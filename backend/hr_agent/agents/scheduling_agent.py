from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hr_agent.config import get_settings
from hr_agent.db.models import Candidate, PipelineStage, SchedulingRecord
from hr_agent.services.email_service import EmailService


class SchedulingState(TypedDict, total=False):
    candidate_id: str
    availability_note: str
    meeting_link: str
    emails_sent: bool
    email_error: str


async def node_build_link(state: SchedulingState, config: RunnableConfig) -> dict[str, Any]:
    settings = get_settings()
    link = f"{settings.default_meeting_base}/lookup/{uuid.uuid4().hex[:12]}"
    return {"meeting_link": link}


async def node_persist_schedule(state: SchedulingState, config: RunnableConfig) -> dict[str, Any]:
    session: AsyncSession = config["configurable"]["session"]
    cand = await session.get(Candidate, state["candidate_id"])
    if not cand:
        raise ValueError("candidate not found")
    q = await session.execute(select(SchedulingRecord).where(SchedulingRecord.candidate_id == cand.id))
    row = q.scalar_one_or_none()
    if not row:
        row = SchedulingRecord(candidate_id=cand.id, availability_note=state.get("availability_note", ""))
        session.add(row)
    row.availability_note = state.get("availability_note", "")
    row.meeting_link = state.get("meeting_link")
    row.confirmed_at = datetime.utcnow()
    await session.flush()
    return {}


async def node_send_emails(state: SchedulingState, config: RunnableConfig) -> dict[str, Any]:
    session: AsyncSession = config["configurable"]["session"]
    settings = get_settings()
    cand = await session.get(Candidate, state["candidate_id"])
    if not cand or not cand.email:
        return {"emails_sent": False}
    mail = EmailService()
    subj = "Interview confirmation"
    body = (
        f"Dear {cand.full_name},\n\nYour interview is scheduled.\n"
        f"Meeting: {state.get('meeting_link')}\n"
        f"Availability noted: {state.get('availability_note')}\n"
    )
    try:
        await mail.send_if_new(
            session,
            template_key="interview_confirm_candidate",
            candidate_id=cand.id,
            recipient=cand.email,
            subject=subj,
            body=body,
        )
        hr_body = (
            f"Candidate {cand.full_name} ({cand.email}) confirmed scheduling.\n"
            f"Link: {state.get('meeting_link')}\n"
        )
        await mail.send_if_new(
            session,
            template_key="interview_confirm_hr",
            candidate_id=cand.id,
            recipient=settings.hr_notify_email,
            subject=f"[HR] Interview scheduled: {cand.full_name}",
            body=hr_body,
        )
    except Exception as exc:
        return {"emails_sent": False, "email_error": str(exc)}
    cand.stage = PipelineStage.INTERVIEW_SCHEDULED
    await session.flush()
    return {"emails_sent": True}


def build_scheduling_graph() -> StateGraph:
    g = StateGraph(SchedulingState)
    g.add_node("link", node_build_link)
    g.add_node("persist", node_persist_schedule)
    g.add_node("mail", node_send_emails)
    g.add_edge(START, "link")
    g.add_edge("link", "persist")
    g.add_edge("persist", "mail")
    g.add_edge("mail", END)
    return g


class SchedulingAgentGraph:
    def __init__(self) -> None:
        self._graph = build_scheduling_graph().compile()

    async def run(self, session: AsyncSession, state: SchedulingState) -> SchedulingState:
        cfg: RunnableConfig = {"configurable": {"session": session}}
        return await self._graph.ainvoke(state, config=cfg)  # type: ignore[return-value]
