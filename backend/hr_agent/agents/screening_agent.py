from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from hr_agent.db.models import Candidate, PipelineStage, ScreeningSession
from hr_agent.services.llm_service import LLMService


class ScreeningState(TypedDict, total=False):
    screening_id: str
    candidate_id: str
    resume_text: str
    questions: list[dict[str, Any]]
    structured_responses: dict[str, Any]
    phase: str


async def node_load_resume(state: ScreeningState, config: RunnableConfig) -> dict[str, Any]:
    session: AsyncSession = config["configurable"]["session"]
    cand = await session.get(Candidate, state["candidate_id"])
    if not cand:
        raise ValueError("candidate not found")
    return {"resume_text": cand.resume_text[:12000]}


async def node_generate_questions(state: ScreeningState, config: RunnableConfig) -> dict[str, Any]:
    llm = LLMService()
    system = (
        "You are an HR screening interviewer. Derive 3-5 questions from the resume context. "
        "Do NOT ask about facts clearly stated in the resume (company names, dates already listed, etc.). "
        "You MUST include at least: notice period / joining availability, and education or student/part-time status. "
        "Return JSON: questions: list of {id, text, topic}."
    )
    user = f"Resume:\n{state.get('resume_text', '')}\n"
    out = await llm.chat_json(system, user)
    qs = out.get("questions")
    if not isinstance(qs, list):
        qs = [
            {"id": "n1", "text": "What is your notice period and earliest joining date?", "topic": "availability"},
            {"id": "e1", "text": "Confirm your graduation year and degree.", "topic": "education"},
        ]
    return {"questions": qs, "phase": "awaiting_answers"}


async def node_persist_questions(state: ScreeningState, config: RunnableConfig) -> dict[str, Any]:
    session: AsyncSession = config["configurable"]["session"]
    row = await session.get(ScreeningSession, state.get("screening_id", ""))
    if row:
        row.questions = state.get("questions", [])
        await session.flush()
    return {}


async def node_persist_answers(state: ScreeningState, config: RunnableConfig) -> dict[str, Any]:
    session: AsyncSession = config["configurable"]["session"]
    row = await session.get(ScreeningSession, state.get("screening_id", ""))
    if not row:
        return {}
    structured = dict(state.get("structured_responses") or {})
    row.structured_responses = structured
    row.completed_at = datetime.utcnow()
    cand = await session.get(Candidate, state["candidate_id"])
    if cand:
        cand.stage = PipelineStage.SCHEDULING
    await session.flush()
    return {"phase": "done"}


def route_start(state: ScreeningState) -> str:
    if state.get("structured_responses") is not None and len(state.get("structured_responses") or {}) > 0:
        return "persist_answers"
    return "load"


def build_screening_graph() -> StateGraph:
    g = StateGraph(ScreeningState)
    g.add_node("load", node_load_resume)
    g.add_node("generate", node_generate_questions)
    g.add_node("persist_questions", node_persist_questions)
    g.add_node("persist_answers", node_persist_answers)
    g.add_conditional_edges(START, route_start, {"load": "load", "persist_answers": "persist_answers"})
    g.add_edge("load", "generate")
    g.add_edge("generate", "persist_questions")
    g.add_edge("persist_questions", END)
    g.add_edge("persist_answers", END)
    return g


class ScreeningAgentGraph:
    def __init__(self) -> None:
        self._graph = build_screening_graph().compile()

    async def run(self, session: AsyncSession, state: ScreeningState) -> ScreeningState:
        cfg: RunnableConfig = {"configurable": {"session": session}}
        return await self._graph.ainvoke(state, config=cfg)  # type: ignore[return-value]
