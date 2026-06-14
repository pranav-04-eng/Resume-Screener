"""Intake business logic (the Service layer between controller and Model).

Responsibilities:
  * generate pre-signed S3 PUT URLs so the browser uploads files directly
  * create the job + candidate records in DynamoDB
  * on submit, enqueue one SQS message per resume (one message == one unit of
    work, which lets KEDA scale the worker on resume count)
"""

from __future__ import annotations

import logging
import uuid
from typing import List

from screener_common import keys
from screener_common.aws import s3_presign_client, sqs_client
from screener_common.models import (
    CreateJobRequest,
    CreateJobResponse,
    JobMessage,
    JobStatus,
    PresignedTarget,
)
from screener_common.repository import JobRepository
from screener_common.settings import settings

log = logging.getLogger("intake.service")


class IntakeService:
    def __init__(self) -> None:
        self.repo = JobRepository()
        self.s3 = s3_presign_client()
        self.sqs = sqs_client()

    def _presign_put(self, key: str, content_type: str) -> str:
        return self.s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.s3_bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=settings.presign_expiry,
        )

    def create_job(self, req: CreateJobRequest) -> CreateJobResponse:
        job_id = uuid.uuid4().hex
        jd_key = keys.jd_key(job_id, req.jd_file_name)

        candidates: List[dict] = []
        resume_targets: List[PresignedTarget] = []
        for spec in req.resumes:
            resume_id = uuid.uuid4().hex
            r_key = keys.resume_key(job_id, resume_id, spec.file_name)
            candidates.append(
                {"resume_id": resume_id, "file_name": spec.file_name, "resume_key": r_key}
            )
            resume_targets.append(
                PresignedTarget(
                    upload_url=self._presign_put(r_key, spec.content_type),
                    key=r_key,
                    resume_id=resume_id,
                    file_name=spec.file_name,
                )
            )

        self.repo.create_job(
            job_id=job_id, title=req.title, jd_key=jd_key, candidates=candidates
        )

        log.info(
            "job created",
            extra={"job_id": job_id, "resume_count": len(candidates)},
        )
        return CreateJobResponse(
            job_id=job_id,
            status=JobStatus.CREATED,
            jd_upload=PresignedTarget(
                upload_url=self._presign_put(jd_key, req.jd_content_type),
                key=jd_key,
                file_name=req.jd_file_name,
            ),
            resume_uploads=resume_targets,
        )

    def submit_job(self, job_id: str) -> JobStatus:
        """Mark uploads complete and enqueue one message per resume."""
        meta = self.repo.get_job_meta(job_id)
        if meta is None:
            raise KeyError(job_id)

        # Re-query candidate items to build messages with their S3 keys.
        results = self.repo.get_job_results(job_id)
        jd_key = meta["jd_key"]

        enqueued = 0
        for cand in results.candidates:  # type: ignore[union-attr]
            # resume_key is reconstructable from convention, but read it back
            # from the stored item to stay authoritative.
            resume_key = keys.resume_key(job_id, cand.resume_id, cand.file_name)
            msg = JobMessage(
                job_id=job_id,
                resume_id=cand.resume_id,
                resume_key=resume_key,
                jd_key=jd_key,
                file_name=cand.file_name,
            )
            self.sqs.send_message(
                QueueUrl=settings.sqs_queue_url,
                MessageBody=msg.model_dump_json(),
            )
            enqueued += 1

        self.repo.mark_queued(job_id)
        log.info("job submitted", extra={"job_id": job_id, "enqueued": enqueued})
        return JobStatus.QUEUED
