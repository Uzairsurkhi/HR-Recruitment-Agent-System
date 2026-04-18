from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from hr_agent.api.deps import get_db
from hr_agent.db.models import Role
from hr_agent.schemas import RoleCreate, RoleOut

router = APIRouter(prefix="/roles", tags=["roles"])


@router.post("", response_model=RoleOut)
async def create_role(body: RoleCreate, session: AsyncSession = Depends(get_db)) -> Role:
    r = Role(
        title=body.title,
        job_description=body.job_description,
        headcount_target=body.headcount_target,
    )
    session.add(r)
    await session.commit()
    await session.refresh(r)
    return r


@router.get("", response_model=list[RoleOut])
async def list_roles(session: AsyncSession = Depends(get_db)) -> list[Role]:
    from sqlalchemy import select

    res = await session.execute(select(Role).order_by(Role.created_at.desc()))
    return list(res.scalars().all())
