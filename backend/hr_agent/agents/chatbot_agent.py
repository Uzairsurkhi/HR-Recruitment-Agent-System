from __future__ import annotations

import json
import re
from typing import Any, Optional, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hr_agent.config import get_settings
from hr_agent.db.models import Candidate, PipelineStage, Role
from hr_agent.services.email_service import EmailService
from hr_agent.services.llm_service import LLMService
from hr_agent.services.rag_service import RAGService


class ChatbotState(TypedDict, total=False):
    user_message: str
    hr_user_id: Optional[str]
    db_facts: str
    tool_results: list[dict[str, Any]]
    reply: str


async def node_ground(state: ChatbotState, config: RunnableConfig) -> dict[str, Any]:
    """RAG: pull structured rows from DB (long-term memory) — never hallucinate candidates."""
    session: AsyncSession = config["configurable"]["session"]
    lines: list[str] = []

    r = await session.execute(
        select(Role.id, Role.title, Role.headcount_target, Role.job_description).limit(50)
    )
    roles = r.all()
    for row in roles:
        lines.append(f"Role {row[0]}: {row[1]} | headcount={row[2]} | JD excerpt={row[3][:400]}...")

    c = await session.execute(
        select(
            Candidate.id,
            Candidate.full_name,
            Candidate.email,
            Candidate.stage,
            Candidate.ats_score,
            Candidate.technical_total_score,
            Candidate.role_id,
        ).limit(200)
    )
    for row in c.all():
        lines.append(
            f"Candidate {row[0]}: {row[1]} | email={row[2]} | stage={row[3]} | "
            f"ats={row[4]} | tech={row[5]} | role_id={row[6]}"
        )

    counts = await session.execute(select(Candidate.stage, func.count()).group_by(Candidate.stage))
    for st, n in counts.all():
        lines.append(f"COUNT stage={st}: {n}")

    facts = "\n".join(lines)
    rag = RAGService()
    resumes = await session.execute(select(Candidate.id, Candidate.resume_text).limit(20))
    snippets = await rag.candidate_snippets_for_chatbot([(str(r[0]), r[1][:4000]) for r in resumes.all()])
    return {"db_facts": facts + "\n\nRAG snippets:\n" + snippets[:8000]}


async def node_tools(state: ChatbotState, config: RunnableConfig) -> dict[str, Any]:
    session: AsyncSession = config["configurable"]["session"]
    msg = (state.get("user_message") or "").strip()
    results: list[dict[str, Any]] = []

    m = re.search(r"set\s+stage\s+(\S+)\s+to\s+(\S+)", msg, re.I)
    if m:
        cid, st = m.group(1), m.group(2)
        try:
            stage = PipelineStage(st)
        except ValueError:
            results.append({"error": f"invalid stage {st}"})
        else:
            cand = await session.get(Candidate, cid)
            if cand:
                cand.stage = stage
                await session.flush()
                results.append({"updated_candidate": cid, "stage": stage.value})
            else:
                results.append({"error": "candidate not found"})

    if re.search(r"create\s+role", msg, re.I):
        title_m = re.search(r"title\s*[:\-]\s*([^\n|]+)", msg, re.I)
        jd_m = re.search(r"jd\s*[:\-]\s*([^\n]+)", msg, re.I)
        title = (title_m.group(1).strip() if title_m else "New role")[:240]
        jd = (jd_m.group(1).strip() if jd_m else "Job description placeholder")[:20000]
        role = Role(title=title, job_description=jd, headcount_target=1, email_template_prepared=True)
        session.add(role)
        await session.flush()
        mail = EmailService()
        await mail.send_if_new(
            session,
            template_key=f"role_outbound:{role.id}",
            candidate_id=None,
            recipient=get_settings().hr_notify_email,
            subject=f"[HR] Role templates ready: {title}",
            body=f"Role {role.id} created. Prepare outbound templates.",
        )
        results.append({"created_role": role.id, "title": title})

    return {"tool_results": results}


async def node_replies(state: ChatbotState, config: RunnableConfig) -> dict[str, Any]:
    llm = LLMService()
    system = (
        "You are an HR assistant. Answer ONLY using the provided DB_FACTS and TOOL_RESULTS. "
        "If information is missing, say you don't have it in the database. "
        "Return JSON with key: reply (string)."
    )
    user = (
        f"USER:\n{state.get('user_message','')}\n\nDB_FACTS:\n{state.get('db_facts','')}\n\n"
        f"TOOL_RESULTS:\n{json.dumps(state.get('tool_results') or [])}\n"
    )
    out = await llm.chat_json(system, user)
    return {"reply": str(out.get("reply", "I could not find that in the database."))}


def build_chatbot_graph() -> StateGraph:
    g = StateGraph(ChatbotState)
    g.add_node("ground", node_ground)
    g.add_node("tools", node_tools)
    g.add_node("reply", node_replies)
    g.add_edge(START, "ground")
    g.add_edge("ground", "tools")
    g.add_edge("tools", "reply")
    g.add_edge("reply", END)
    return g


class ChatbotAgentGraph:
    def __init__(self) -> None:
        self._graph = build_chatbot_graph().compile()

    async def run(self, session: AsyncSession, state: ChatbotState) -> ChatbotState:
        cfg: RunnableConfig = {"configurable": {"session": session}}
        return await self._graph.ainvoke(state, config=cfg)  # type: ignore[return-value]
