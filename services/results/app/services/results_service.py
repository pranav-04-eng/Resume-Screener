"""Results read logic (Service layer).

Pure read side over the shared repository. Ranking is derived at read time
(repository sorts candidates by score), so the worker never has to coordinate
across resumes to assign ranks.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from screener_common.models import JobResults, JobSummary
from screener_common.repository import JobRepository

log = logging.getLogger("results.service")


class ResultsService:
    def __init__(self) -> None:
        self.repo = JobRepository()

    def list_jobs(self, limit: int = 50) -> List[JobSummary]:
        return self.repo.list_jobs(limit=limit)

    def get_job(self, job_id: str) -> Optional[JobResults]:
        return self.repo.get_job_results(job_id)
