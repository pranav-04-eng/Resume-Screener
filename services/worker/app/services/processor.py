"""Processes a single SQS message end-to-end.

  download resume + JD from S3 -> extract text -> LLM extract -> LLM score
  -> write result to DynamoDB.

JD text is cached per job_id so a batch of resumes for one job extracts the JD
only once.
"""

from __future__ import annotations

import logging

from app.pipeline.extract import extract_fields
from app.pipeline.score import score_candidate
from app.services.text_extract import extract_text
from screener_common.aws import s3_client
from screener_common.models import JobMessage
from screener_common.repository import JobRepository
from screener_common.settings import settings

log = logging.getLogger("worker.processor")


class Processor:
    def __init__(self) -> None:
        self.repo = JobRepository()
        self.s3 = s3_client()
        self._jd_cache: dict[str, str] = {}

    def _download(self, key: str) -> bytes:
        obj = self.s3.get_object(Bucket=settings.s3_bucket, Key=key)
        return obj["Body"].read()

    def _jd_text(self, job_id: str, jd_key: str) -> str:
        if job_id not in self._jd_cache:
            jd_name = jd_key.rsplit("/", 1)[-1]
            self._jd_cache[job_id] = extract_text(jd_name, self._download(jd_key))
        return self._jd_cache[job_id]

    def process(self, msg: JobMessage) -> None:
        """Run the full pipeline for one resume.

        Raises on failure so the consumer loop can decide whether to retry
        (SQS redelivery) or treat it as terminal (record FAILED + send to DLQ).
        """
        ctx = {"job_id": msg.job_id, "resume_id": msg.resume_id}
        log.info("processing resume", extra=ctx)
        self.repo.mark_candidate_processing(msg.job_id, msg.resume_id)

        jd_text = self._jd_text(msg.job_id, msg.jd_key)
        resume_text = extract_text(msg.file_name, self._download(msg.resume_key))
        if not resume_text.strip():
            raise ValueError("no extractable text in resume")

        extracted = extract_fields(resume_text)
        score = score_candidate(jd_text, extracted, resume_text)

        self.repo.save_candidate_result(
            job_id=msg.job_id,
            resume_id=msg.resume_id,
            extracted=extracted,
            score=score,
        )
        log.info("resume scored", extra={**ctx, "score": score.score})

    def mark_failed(self, msg: JobMessage, error: str) -> None:
        self.repo.mark_candidate_failed(msg.job_id, msg.resume_id, error)
