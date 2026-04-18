from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from hr_agent.config import get_settings
from hr_agent.db.models import Candidate, PipelineStage, Role, TechnicalInterviewSession
from hr_agent.services.llm_service import LLMService


class TIState(TypedDict, total=False):
    """Session state: Q&A and scores accumulate without re-fetching prior rows from DB."""

    session_id: str
    candidate_id: str
    experience_level: str
    resume_excerpt: str
    jd_excerpt: str
    question_index: int
    current_question: str
    last_answer: Optional[str]
    transcript: list[dict[str, Any]]
    phase: Literal["generate", "evaluate", "finalize"]
    done: bool


async def _load_context(state: TIState, session: AsyncSession) -> dict[str, Any]:
    cand = await session.get(Candidate, state["candidate_id"])
    if not cand:
        raise ValueError("candidate not found")
    role = await session.get(Role, cand.role_id)
    jd = role.job_description if role else ""
    return {
        "resume_excerpt": cand.resume_text[:6000],
        "jd_excerpt": jd[:6000],
    }


async def node_generate_question(state: TIState, config: RunnableConfig) -> dict[str, Any]:
    session: AsyncSession = config["configurable"]["session"]
    merged = await _load_context(state, session)
    llm = LLMService()
    level = state.get("experience_level", "mid")
    system = (
        "You generate one technical interview question appropriate for the role and experience level. "
        "Return JSON with key: question (string). Question must be answerable in a short paragraph."
    )
    user = (
        f"Experience level: {level}. JD excerpt:\n{merged['jd_excerpt'][:4000]}\n\n"
        f"Resume excerpt:\n{merged['resume_excerpt'][:4000]}\n"
    )
    out = await llm.chat_json(system, user)
    q = str(out.get("question", "Describe a recent technical challenge you solved."))
    return {
        **merged,
        "current_question": q,
        "phase": "generate",
        "last_answer": None,
    }


async def node_evaluate(state: TIState, config: RunnableConfig) -> dict[str, Any]:
    session: AsyncSession = config["configurable"]["session"]
    llm = LLMService()
    system = (
        "Evaluate the answer. Return JSON: score (0-10 float), reasoning (string). "
        "Be strict but fair for the stated experience level."
    )
    user = (
        f"Level: {state.get('experience_level', 'mid')}\n"
        f"Question: {state.get('current_question', '')}\n"
        f"Answer: {state.get('last_answer', '')}\n"
    )
    out = await llm.chat_json(system, user)
    score = float(out.get("score", 0))
    reasoning = str(out.get("reasoning", ""))
    entry = {
        "question": state.get("current_question", ""),
        "answer": state.get("last_answer"),
        "score": score,
        "reasoning": reasoning,
    }
    transcript = list(state.get("transcript") or [])
    transcript.append(entry)
    settings = get_settings()
    next_idx = int(state.get("question_index", 0)) + 1
    done = next_idx >= settings.interview_question_count
    sess = await session.get(TechnicalInterviewSession, state.get("session_id", ""))
    if sess:
        sess.transcript = transcript
        await session.flush()
    return {
        "transcript": transcript,
        "question_index": next_idx,
        "last_answer": None,
        "phase": "finalize" if done else "generate",
        "done": done,
    }


async def node_finalize(state: TIState, config: RunnableConfig) -> dict[str, Any]:
    session: AsyncSession = config["configurable"]["session"]
    sess = await session.get(TechnicalInterviewSession, state.get("session_id", ""))
    if not sess:
        return {"done": True}
    scores = [float(x["score"]) for x in state.get("transcript", []) if "score" in x]
    total = sum(scores) / max(len(scores), 1) if scores else 0.0
    sess.transcript = state.get("transcript", [])
    sess.total_score = total
    sess.completed_at = datetime.utcnow()
    cand = await session.get(Candidate, state.get("candidate_id", ""))
    if cand:
        cand.technical_total_score = total
        cand.stage = PipelineStage.HR_SCREENING
    await session.flush()
    return {"done": True}


def entry_route(state: TIState) -> str:
    if state.get("last_answer"):
        return "evaluate"
    return "generate"


def after_eval(state: TIState) -> str:
    if state.get("done"):
        return "finalize"
    return "generate"


def build_technical_interview_graph() -> StateGraph:
    g = StateGraph(TIState)
    g.add_node("generate", node_generate_question)
    g.add_node("evaluate", node_evaluate)
    g.add_node("finalize", node_finalize)
    g.add_conditional_edges(START, entry_route, {"generate": "generate", "evaluate": "evaluate"})
    g.add_conditional_edges("evaluate", after_eval, {"finalize": "finalize", "generate": "generate"})
    g.add_edge("generate", END)
    g.add_edge("finalize", END)
    return g


class TechnicalInterviewGraph:
    def __init__(self) -> None:
        self._graph = build_technical_interview_graph().compile()

    async def run_turn(self, session: AsyncSession, state: TIState) -> TIState:
        cfg: RunnableConfig = {"configurable": {"session": session}}
        result = await self._graph.ainvoke(state, config=cfg)
        return result  # type: ignore[return-value]
