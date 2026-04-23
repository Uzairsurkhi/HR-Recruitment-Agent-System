from __future__ import annotations

import logging
import re
from typing import Any, Optional, TypedDict

from langchain_core.runnables import RunnableConfig  # pyright: ignore[reportMissingImports]
from langgraph.graph import END, StateGraph  # pyright: ignore[reportMissingImports]
from sqlalchemy.ext.asyncio import AsyncSession  # pyright: ignore[reportMissingImports]

from hr_agent.config import get_settings
from hr_agent.db.models import Candidate, PipelineStage
from hr_agent.services.email_service import EmailService
from hr_agent.services.llm_service import LLMService
from hr_agent.services.rag_service import RAGService


logger = logging.getLogger(__name__)


class ATSState(TypedDict):
    """Short-term LangGraph state: resume + JD context flows through nodes (not re-fetched)."""

    candidate_id: str
    role_id: str
    resume_text: str
    jd_text: str
    full_name: str
    email: Optional[str]
    rag_context: str
    retrieval_score: float
    skill_match: float
    experience_alignment: float
    keyword_relevance: float
    overall_score: float
    rationale: str
    rejection_sent: bool


def _extract_email(text: str) -> Optional[str]:
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]{2,}", text)
    return m.group(0) if m else None


async def node_rag(state: ATSState, config: RunnableConfig) -> dict[str, Any]:
    rag = RAGService()
    ctx = await rag.build_ats_context(state["resume_text"], state["jd_text"])
    return {
        "rag_context": ctx["context_for_llm"],
        "retrieval_score": float(ctx["retrieval_score"]),
    }


async def node_score_llm(state: ATSState, config: RunnableConfig) -> dict[str, Any]:
    llm = LLMService()
    system = (
        "You are an ATS scoring engine. Score the candidate against the job description. "
        "Return ONLY valid JSON with keys: skill_match, experience_alignment, keyword_relevance "
        "(each 0-1 float), overall_score (0-100 float), rationale (string). "
        "overall_score must combine skill_match, experience_alignment, keyword_relevance with ATS weighting."
    )
    user = (
        f"Job description:\n{state['jd_text'][:12000]}\n\n"
        f"RAG resume chunks (retrieval vs JD):\n{state['rag_context'][:12000]}\n\n"
        f"Full resume:\n{state['resume_text'][:12000]}\n"
    )
    out = await llm.chat_json(system, user)

    # Parse and clamp all component scores for stable ATS calibration.
    skill = max(0.0, min(1.0, float(out.get("skill_match", 0))))
    exp = max(0.0, min(1.0, float(out.get("experience_alignment", 0))))
    kw = max(0.0, min(1.0, float(out.get("keyword_relevance", 0))))
    model_overall = max(0.0, min(100.0, float(out.get("overall_score", 0))))
    retrieval = max(0.0, min(1.0, float(state.get("retrieval_score", 0))))

    # Blend LLM score with deterministic feature signal to reduce under-scoring on
    # strong profiles where individual components are high.
    feature_overall = (skill * 0.35 + exp * 0.35 + kw * 0.2 + retrieval * 0.1) * 100.0
    calibrated_overall = round(
        max(model_overall, 0.65 * model_overall + 0.35 * feature_overall + 4.0),
        1,
    )
    overall = max(0.0, min(100.0, calibrated_overall))

    settings = get_settings()
    ats_cap = max(0.0, min(100.0, float(settings.ats_score_max)))
    if overall > ats_cap:
        overall = round(ats_cap, 1)

    rationale = str(out.get("rationale", "")).strip()
    if rationale:
        rationale = rationale + " "
    rationale += (
        f"Calibrated ATS score from model and feature signal (retrieval={retrieval:.2f})."
    )
    if calibrated_overall > ats_cap:
        rationale += f" Capped at {ats_cap} (ats_score_max)."

    return {
        "skill_match": skill,
        "experience_alignment": exp,
        "keyword_relevance": kw,
        "overall_score": overall,
        "rationale": rationale,
    }


async def node_persist(state: ATSState, config: RunnableConfig) -> dict[str, Any]:
    session: AsyncSession = config["configurable"]["session"]
    cand = await session.get(Candidate, state["candidate_id"])
    if not cand:
        return {}
    email = state.get("email") or _extract_email(state["resume_text"])
    cand.email = email
    cand.ats_score = state["overall_score"]
    cand.ats_breakdown = {
        "skill_match": state["skill_match"],
        "experience_alignment": state["experience_alignment"],
        "keyword_relevance": state["keyword_relevance"],
        "retrieval_score": state["retrieval_score"],
        "rationale": state["rationale"],
    }
    settings = get_settings()
    if state["overall_score"] >= settings.ats_pass_threshold:
        cand.stage = PipelineStage.TECHNICAL
    else:
        cand.stage = PipelineStage.ATS_REJECTED
    await session.flush()
    return {}


async def node_rejection_email(state: ATSState, config: RunnableConfig) -> dict[str, Any]:
    settings = get_settings()
    if state["overall_score"] >= settings.ats_pass_threshold:
        return {"rejection_sent": False}
    session: AsyncSession = config["configurable"]["session"]
    cand = await session.get(Candidate, state["candidate_id"])
    if not cand or not cand.email:
        return {"rejection_sent": False}
    mail = EmailService()
    subj = "Application update"
    body = (
        f"Dear {cand.full_name},\n\nThank you for applying. After review, we will not be moving forward.\n\n"
        f"ATS score: {state['overall_score']:.1f}.\n"
    )
    try:
        sent = await mail.send_if_new(
            session,
            template_key="ats_rejection",
            candidate_id=cand.id,
            recipient=cand.email,
            subject=subj,
            body=body,
        )
        return {"rejection_sent": bool(sent)}
    except Exception:
        # Email delivery should not fail the ATS pipeline.
        logger.exception("ATS rejection email send failed for candidate_id=%s", cand.id)
        return {"rejection_sent": False}


def route_after_persist(state: ATSState) -> str:
    settings = get_settings()
    if state["overall_score"] >= settings.ats_pass_threshold:
        return "end"
    return "reject_mail"


def build_ats_graph() -> StateGraph:
    g = StateGraph(ATSState)
    g.add_node("rag", node_rag)
    g.add_node("score", node_score_llm)
    g.add_node("persist", node_persist)
    g.add_node("reject_mail", node_rejection_email)
    g.set_entry_point("rag")
    g.add_edge("rag", "score")
    g.add_edge("score", "persist")
    g.add_conditional_edges(
        "persist",
        route_after_persist,
        {"end": END, "reject_mail": "reject_mail"},
    )
    g.add_edge("reject_mail", END)
    return g


class ATSAgentGraph:
    """OO wrapper: compile once, invoke with DB session in config."""

    def __init__(self) -> None:
        self._graph = build_ats_graph().compile()

    async def run(self, session: AsyncSession, state: ATSState) -> ATSState:
        cfg: RunnableConfig = {"configurable": {"session": session}}
        result = await self._graph.ainvoke(state, config=cfg)
        return result  # type: ignore[return-value]
