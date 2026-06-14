"""Domain models and the cross-service message/item contracts.

These Pydantic models are the *Model* layer in the MVC sense — they define the
shapes that flow through the API, into DynamoDB, and across SQS. Every service
imports from here so the contract can never drift between producer and
consumer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── State machines ──────────────────────────────────────────────────────────
class JobStatus(str, Enum):
    CREATED = "CREATED"        # job + candidate records exist, awaiting uploads
    QUEUED = "QUEUED"          # files uploaded, messages enqueued to SQS
    PROCESSING = "PROCESSING"  # at least one resume scored
    COMPLETED = "COMPLETED"    # all resumes scored or failed
    FAILED = "FAILED"          # unrecoverable job-level failure


class CandidateStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SCORED = "SCORED"
    FAILED = "FAILED"


# ── LLM pipeline output (extract -> score) ──────────────────────────────────
class ExtractedFields(BaseModel):
    """Structured fields the LLM pulls out of a raw resume."""

    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    years_experience: Optional[float] = None
    current_title: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    education: List[str] = Field(default_factory=list)
    companies: List[str] = Field(default_factory=list)


class ScoreResult(BaseModel):
    """How well a candidate matches the JD (absolute, 0-100)."""

    score: float = Field(ge=0, le=100)
    summary: str = ""
    strengths: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)


# ── SQS message: one per resume (lets KEDA scale on resume count) ───────────
class JobMessage(BaseModel):
    job_id: str
    resume_id: str
    resume_key: str
    jd_key: str
    file_name: str


# ── API request/response models ─────────────────────────────────────────────
class ResumeUploadSpec(BaseModel):
    file_name: str
    content_type: str = "application/octet-stream"


class CreateJobRequest(BaseModel):
    title: str
    jd_file_name: str
    jd_content_type: str = "application/octet-stream"
    resumes: List[ResumeUploadSpec] = Field(min_length=1)


class PresignedTarget(BaseModel):
    """A single pre-signed PUT the browser uploads directly to."""

    upload_url: str
    key: str
    # echoed back so the client knows which resume this URL belongs to
    resume_id: Optional[str] = None
    file_name: str


class CreateJobResponse(BaseModel):
    job_id: str
    status: JobStatus
    jd_upload: PresignedTarget
    resume_uploads: List[PresignedTarget]


class CandidateResult(BaseModel):
    resume_id: str
    file_name: str
    status: CandidateStatus
    rank: Optional[int] = None
    score: Optional[float] = None
    summary: Optional[str] = None
    strengths: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    extracted: Optional[ExtractedFields] = None
    error: Optional[str] = None


class JobSummary(BaseModel):
    job_id: str
    title: str
    status: JobStatus
    created_at: str
    total_resumes: int
    processed_resumes: int
    failed_resumes: int


class JobResults(JobSummary):
    candidates: List[CandidateResult] = Field(default_factory=list)
