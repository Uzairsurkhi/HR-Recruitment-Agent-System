from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import OperationalError
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
    try:
        await session.commit()
    except OperationalError as exc:
        await session.rollback()
        msg = str(exc).lower()
        if "database is locked" in msg:
            raise HTTPException(503, "Database is busy/locked. Close DB Browser write session and retry.")
        raise
    await session.refresh(r)
    return r


@router.get("", response_model=list[RoleOut])
async def list_roles(session: AsyncSession = Depends(get_db)) -> list[Role]:
    from sqlalchemy import select

    try:
        res = await session.execute(select(Role).order_by(Role.created_at.desc()))
    except OperationalError as exc:
        if "database is locked" in str(exc).lower():
            raise HTTPException(503, "Database is busy/locked. Close DB Browser write session and retry.")
        raise
    return list(res.scalars().all())
