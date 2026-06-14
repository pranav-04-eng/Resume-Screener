"""HTTP controller for the results/query API."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, Query

from app.services.results_service import ResultsService
from screener_common.models import JobResults, JobSummary

router = APIRouter(prefix="/jobs", tags=["results"])
_service = ResultsService()


@router.get("", response_model=List[JobSummary])
def list_jobs(limit: int = Query(50, ge=1, le=200)) -> List[JobSummary]:
    """List jobs, newest first (status + progress counters)."""
    return _service.list_jobs(limit=limit)


@router.get("/{job_id}", response_model=JobResults)
def get_job(job_id: str) -> JobResults:
    """Full job status + ranked candidate results."""
    results = _service.get_job(job_id)
    if results is None:
        raise HTTPException(status_code=404, detail="job not found")
    return results
