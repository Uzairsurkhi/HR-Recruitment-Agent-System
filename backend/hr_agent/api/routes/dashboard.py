from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hr_agent.api.deps import get_db
from hr_agent.db.models import Candidate, PipelineStage, Role
from hr_agent.schemas import CandidateOut, DashboardSummary, RoleOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
async def summary(
    session: AsyncSession = Depends(get_db),
    role_id: Optional[str] = Query(None),
    stage: Optional[str] = Query(None),
) -> DashboardSummary:
    rres = await session.execute(select(Role).order_by(Role.created_at.desc()))
    roles = list(rres.scalars().all())
    cq = select(Candidate)
    if role_id:
        cq = cq.where(Candidate.role_id == role_id)
    if stage:
        try:
            st = PipelineStage(stage)
            cq = cq.where(Candidate.stage == st)
        except ValueError:
            pass
    cres = await session.execute(cq.order_by(Candidate.created_at.desc()))
    candidates = list(cres.scalars().all())

    counts: dict[str, int] = {}
    for st in PipelineStage:
        counts[st.value] = 0
    cntres = await session.execute(select(Candidate.stage, func.count()).group_by(Candidate.stage))
    for st, n in cntres.all():
        counts[st.value] = int(n)

    return DashboardSummary(
        roles=[RoleOut.model_validate(x) for x in roles],
        candidates=[CandidateOut.model_validate(x) for x in candidates],
        stage_counts=counts,
    )
