from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ExperienceLevelEnum(str, Enum):
    junior = "junior"
    mid = "mid"
    senior = "senior"


class PipelineStageEnum(str, Enum):
    applied = "applied"
    ats_rejected = "ats_rejected"
    technical_interview = "technical_interview"
    hr_screening = "hr_screening"
    scheduling = "scheduling"
    interview_scheduled = "interview_scheduled"
    offer = "offer"


class RoleCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=255)
    job_description: str = Field(..., min_length=20)
    headcount_target: int = Field(1, ge=1, le=1000)


class RoleOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    title: str
    headcount_target: int
    email_template_prepared: bool
    created_at: datetime


class CandidateUpload(BaseModel):
    role_id: str
    full_name: str = Field(..., min_length=2, max_length=255)
    experience_level: ExperienceLevelEnum = ExperienceLevelEnum.mid


class CandidateOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    role_id: str
    full_name: str
    email: Optional[str]
    ats_score: Optional[float]
    stage: PipelineStageEnum
    technical_total_score: Optional[float]
    created_at: datetime


class DashboardSummary(BaseModel):
    roles: List[RoleOut]
    candidates: List[CandidateOut]
    stage_counts: Dict[str, int]


class ScreeningAnswersIn(BaseModel):
    responses: Dict[str, str] = Field(default_factory=dict)
    notice_period: Optional[str] = None
    joining_earliest: Optional[str] = None
    graduation_year: Optional[str] = None
    part_time: Optional[bool] = None


class SchedulingIn(BaseModel):
    """At least one non-space character; typical notes are longer."""
    availability_note: str = Field(..., min_length=1, max_length=8000)


class StageUpdateIn(BaseModel):
    stage: PipelineStageEnum


class ChatMessageIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
