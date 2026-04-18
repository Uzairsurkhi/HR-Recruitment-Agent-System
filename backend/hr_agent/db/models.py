import enum
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.sqlite import CHAR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


class PipelineStage(str, enum.Enum):
    APPLIED = "applied"
    ATS_REJECTED = "ats_rejected"
    TECHNICAL = "technical_interview"
    HR_SCREENING = "hr_screening"
    SCHEDULING = "scheduling"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    OFFER = "offer"


class ExperienceLevel(str, enum.Enum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    job_description: Mapped[str] = mapped_column(Text, nullable=False)
    headcount_target: Mapped[int] = mapped_column(Integer, default=1)
    email_template_prepared: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    candidates: Mapped[List["Candidate"]] = relationship(back_populates="role")


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=_uuid)
    role_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("roles.id"), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    resume_text: Mapped[str] = mapped_column(Text, nullable=False)
    ats_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ats_breakdown: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    stage: Mapped[PipelineStage] = mapped_column(
        Enum(PipelineStage), default=PipelineStage.APPLIED
    )
    technical_total_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    role: Mapped["Role"] = relationship(back_populates="candidates")
    technical_sessions: Mapped[list["TechnicalInterviewSession"]] = relationship(
        back_populates="candidate"
    )
    screening_sessions: Mapped[list["ScreeningSession"]] = relationship(back_populates="candidate")
    scheduling: Mapped[Optional["SchedulingRecord"]] = relationship(back_populates="candidate")


class TechnicalInterviewSession(Base):
    __tablename__ = "technical_interview_sessions"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("candidates.id"), nullable=False)
    experience_level: Mapped[ExperienceLevel] = mapped_column(Enum(ExperienceLevel), nullable=False)
    transcript: Mapped[List[Any]] = mapped_column(JSON, default=list)
    total_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    candidate: Mapped["Candidate"] = relationship(back_populates="technical_sessions")


class ScreeningSession(Base):
    __tablename__ = "screening_sessions"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("candidates.id"), nullable=False)
    questions: Mapped[List[Any]] = mapped_column(JSON, default=list)
    structured_responses: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    candidate: Mapped["Candidate"] = relationship(back_populates="screening_sessions")


class SchedulingRecord(Base):
    __tablename__ = "scheduling_records"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(CHAR(36), ForeignKey("candidates.id"), nullable=False, unique=True)
    availability_note: Mapped[str] = mapped_column(Text, default="")
    meeting_link: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    candidate: Mapped["Candidate"] = relationship(back_populates="scheduling")


class EmailLog(Base):
    __tablename__ = "email_logs"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[Optional[str]] = mapped_column(CHAR(36), ForeignKey("candidates.id"), nullable=True)
    template_key: Mapped[str] = mapped_column(String(128), nullable=False)
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(512), default="")
    body_preview: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("template_key", "candidate_id", name="uq_email_template_candidate"),)
