"""HTTP controller for intake (the Controller layer).

Thin: validates input via Pydantic models, delegates to IntakeService, maps
domain errors to HTTP status codes.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.services.intake_service import IntakeService
from screener_common.models import CreateJobRequest, CreateJobResponse

router = APIRouter(prefix="/jobs", tags=["intake"])
_service = IntakeService()


@router.post("", response_model=CreateJobResponse, status_code=status.HTTP_201_CREATED)
def create_job(req: CreateJobRequest) -> CreateJobResponse:
    """Create a job and return pre-signed URLs for direct-to-S3 upload."""
    return _service.create_job(req)


@router.post("/{job_id}/submit", status_code=status.HTTP_202_ACCEPTED)
def submit_job(job_id: str) -> dict:
    """Signal uploads are complete; enqueue resumes for scoring."""
    try:
        new_status = _service.submit_job(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job_id": job_id, "status": new_status}
