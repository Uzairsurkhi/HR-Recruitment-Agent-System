from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from hr_agent.agents.ats_agent import ATSAgentGraph
from hr_agent.agents.scheduling_agent import SchedulingAgentGraph
from hr_agent.agents.screening_agent import ScreeningAgentGraph
from hr_agent.api.deps import get_db
from hr_agent.db.models import (
    Candidate,
    ExperienceLevel,
    PipelineStage,
    Role,
    ScreeningSession,
    TechnicalInterviewSession,
)
from hr_agent.schemas import CandidateOut, ScreeningAnswersIn, SchedulingIn
from hr_agent.services.resume_parser import extract_text_from_upload

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.post("/upload", response_model=CandidateOut)
async def upload_resume(
    session: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
    role_id: str = Form(...),
    full_name: str = Form(...),
    experience_level: str = Form("mid"),
) -> Candidate:
    role = await session.get(Role, role_id)
    if not role:
        raise HTTPException(404, "role not found")
    raw = await file.read()
    text = await extract_text_from_upload(file.filename or "resume.txt", raw)
    cand = Candidate(
        role_id=role_id,
        full_name=full_name,
        resume_text=text,
        stage=PipelineStage.APPLIED,
    )
    session.add(cand)
    await session.flush()

    agent = ATSAgentGraph()
    await agent.run(
        session,
        {
            "candidate_id": cand.id,
            "role_id": role_id,
            "resume_text": text,
            "jd_text": role.job_description,
            "full_name": full_name,
            "email": None,
            "rag_context": "",
            "retrieval_score": 0.0,
            "skill_match": 0.0,
            "experience_alignment": 0.0,
            "keyword_relevance": 0.0,
            "overall_score": 0.0,
            "rationale": "",
            "rejection_sent": False,
        },
    )
    await session.commit()
    await session.refresh(cand)
    return cand


@router.post("/{candidate_id}/screening/start", response_model=dict)
async def screening_start(candidate_id: str, session: AsyncSession = Depends(get_db)) -> dict:
    cand = await session.get(Candidate, candidate_id)
    if not cand:
        raise HTTPException(404, "candidate not found")
    if cand.stage != PipelineStage.HR_SCREENING:
        raise HTTPException(400, "candidate not in HR screening stage")
    sid = str(uuid.uuid4())
    row = ScreeningSession(id=sid, candidate_id=candidate_id, questions=[], structured_responses={})
    session.add(row)
    await session.flush()
    graph = ScreeningAgentGraph()
    out = await graph.run(
        session,
        {"screening_id": sid, "candidate_id": candidate_id, "phase": "init"},
    )
    await session.commit()
    return {"screening_id": sid, "questions": out.get("questions", [])}


@router.post("/{candidate_id}/screening/submit", response_model=dict)
async def screening_submit(
    candidate_id: str,
    body: ScreeningAnswersIn,
    session: AsyncSession = Depends(get_db),
) -> dict:
    cand = await session.get(Candidate, candidate_id)
    if not cand:
        raise HTTPException(404, "candidate not found")
    from sqlalchemy import select

    q = await session.execute(
        select(ScreeningSession)
        .where(ScreeningSession.candidate_id == candidate_id)
        .order_by(ScreeningSession.created_at.desc())
    )
    row = q.scalars().first()
    if not row:
        raise HTTPException(400, "no screening session")
    structured = {
        "responses": body.responses,
        "notice_period": body.notice_period,
        "joining_earliest": body.joining_earliest,
        "graduation_year": body.graduation_year,
        "part_time": body.part_time,
    }
    graph = ScreeningAgentGraph()
    await graph.run(
        session,
        {
            "screening_id": row.id,
            "candidate_id": candidate_id,
            "structured_responses": structured,
        },
    )
    await session.commit()
    return {"ok": True}


@router.post("/{candidate_id}/schedule", response_model=dict)
async def schedule(
    candidate_id: str,
    body: SchedulingIn,
    session: AsyncSession = Depends(get_db),
) -> dict:
    cand = await session.get(Candidate, candidate_id)
    if not cand:
        raise HTTPException(404, "candidate not found")
    if cand.stage != PipelineStage.SCHEDULING:
        raise HTTPException(400, "candidate not in scheduling stage")
    if body.candidate_email:
        cand.email = body.candidate_email.strip()
    graph = SchedulingAgentGraph()
    out = await graph.run(
        session,
        {"candidate_id": candidate_id, "availability_note": body.availability_note},
    )
    await session.commit()
    return {
        "ok": True,
        "meeting_link": out.get("meeting_link"),
        "emails_sent": out.get("emails_sent"),
        "email_error": out.get("email_error"),
    }


@router.post("/{candidate_id}/technical/start", response_model=dict)
async def technical_start(
    candidate_id: str,
    experience_level: str = "mid",
    session: AsyncSession = Depends(get_db),
) -> dict:
    cand = await session.get(Candidate, candidate_id)
    if not cand:
        raise HTTPException(404, "candidate not found")
    if cand.stage != PipelineStage.TECHNICAL:
        raise HTTPException(400, "candidate not ready for technical interview")
    try:
        exp = ExperienceLevel(experience_level.lower())
    except ValueError:
        exp = ExperienceLevel.MID
    sid = str(uuid.uuid4())
    row = TechnicalInterviewSession(
        id=sid,
        candidate_id=candidate_id,
        experience_level=exp,
        transcript=[],
    )
    session.add(row)
    await session.commit()
    return {"session_id": sid, "experience_level": exp.value}
