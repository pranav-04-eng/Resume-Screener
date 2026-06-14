"""DynamoDB data-access layer (the persistence half of the Model).

All three services share this so the single-table access patterns live in one
place. Methods are intentionally small and side-effect-explicit.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import List, Optional

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from screener_common import keys
from screener_common.aws import jobs_table
from screener_common.models import (
    CandidateResult,
    CandidateStatus,
    ExtractedFields,
    JobResults,
    JobStatus,
    JobSummary,
    ScoreResult,
    utcnow_iso,
)


def _to_ddb(model) -> dict:
    """Pydantic model -> DynamoDB-safe dict (floats become Decimal)."""
    return json.loads(model.model_dump_json(), parse_float=Decimal)


def _to_native(obj):
    """DynamoDB returns Decimal for numbers; normalise for Pydantic/JSON."""
    if isinstance(obj, list):
        return [_to_native(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    return obj


class JobRepository:
    def __init__(self):
        self.table = jobs_table()

    # ── writes (intake) ──────────────────────────────────────────────────
    def create_job(
        self,
        *,
        job_id: str,
        title: str,
        jd_key: str,
        candidates: List[dict],
    ) -> None:
        """Atomically create the META item plus one item per candidate."""
        now = utcnow_iso()
        with self.table.batch_writer() as batch:
            batch.put_item(
                Item={
                    "PK": keys.job_pk(job_id),
                    "SK": keys.META_SK,
                    "GSI1PK": keys.JOBS_GSI1PK,
                    "GSI1SK": now,
                    "entity": "JOB",
                    "job_id": job_id,
                    "title": title,
                    "jd_key": jd_key,
                    "status": JobStatus.CREATED.value,
                    "created_at": now,
                    "updated_at": now,
                    "total_resumes": len(candidates),
                    "processed_resumes": 0,
                    "failed_resumes": 0,
                }
            )
            for c in candidates:
                batch.put_item(
                    Item={
                        "PK": keys.job_pk(job_id),
                        "SK": keys.candidate_sk(c["resume_id"]),
                        "entity": "CANDIDATE",
                        "job_id": job_id,
                        "resume_id": c["resume_id"],
                        "file_name": c["file_name"],
                        "resume_key": c["resume_key"],
                        "status": CandidateStatus.PENDING.value,
                        "created_at": now,
                    }
                )

    def mark_queued(self, job_id: str) -> None:
        self.table.update_item(
            Key={"PK": keys.job_pk(job_id), "SK": keys.META_SK},
            UpdateExpression="SET #s = :q, updated_at = :u",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":q": JobStatus.QUEUED.value,
                ":u": utcnow_iso(),
            },
        )

    # ── writes (worker) ──────────────────────────────────────────────────
    def mark_candidate_processing(self, job_id: str, resume_id: str) -> None:
        self.table.update_item(
            Key={"PK": keys.job_pk(job_id), "SK": keys.candidate_sk(resume_id)},
            UpdateExpression="SET #s = :p",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":p": CandidateStatus.PROCESSING.value},
        )
        # First resume to start flips the job into PROCESSING; subsequent
        # resumes hit the condition and the failure is expected/ignored.
        try:
            self.table.update_item(
                Key={"PK": keys.job_pk(job_id), "SK": keys.META_SK},
                UpdateExpression="SET #s = :p, updated_at = :u",
                ConditionExpression="#s = :queued",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":p": JobStatus.PROCESSING.value,
                    ":queued": JobStatus.QUEUED.value,
                    ":u": utcnow_iso(),
                },
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise

    def save_candidate_result(
        self,
        *,
        job_id: str,
        resume_id: str,
        extracted: ExtractedFields,
        score: ScoreResult,
    ) -> None:
        self.table.update_item(
            Key={"PK": keys.job_pk(job_id), "SK": keys.candidate_sk(resume_id)},
            UpdateExpression=(
                "SET #s = :scored, extracted = :e, score = :sc, summary = :sm, "
                "strengths = :st, gaps = :g, processed_at = :pa"
            ),
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":scored": CandidateStatus.SCORED.value,
                ":e": _to_ddb(extracted),
                ":sc": Decimal(str(score.score)),
                ":sm": score.summary,
                ":st": score.strengths,
                ":g": score.gaps,
                ":pa": utcnow_iso(),
            },
        )
        self._bump_counter(job_id, "processed_resumes")

    def mark_candidate_failed(self, job_id: str, resume_id: str, error: str) -> None:
        self.table.update_item(
            Key={"PK": keys.job_pk(job_id), "SK": keys.candidate_sk(resume_id)},
            UpdateExpression="SET #s = :f, #err = :e, processed_at = :pa",
            ExpressionAttributeNames={"#s": "status", "#err": "error"},
            ExpressionAttributeValues={
                ":f": CandidateStatus.FAILED.value,
                ":e": error[:1000],
                ":pa": utcnow_iso(),
            },
        )
        self._bump_counter(job_id, "failed_resumes")

    def _bump_counter(self, job_id: str, attr: str) -> None:
        """Atomically increment a counter, then complete the job if done."""
        resp = self.table.update_item(
            Key={"PK": keys.job_pk(job_id), "SK": keys.META_SK},
            UpdateExpression="ADD #c :one SET updated_at = :u",
            ExpressionAttributeNames={"#c": attr},
            ExpressionAttributeValues={":one": 1, ":u": utcnow_iso()},
            ReturnValues="ALL_NEW",
        )
        meta = resp["Attributes"]
        done = int(meta["processed_resumes"]) + int(meta["failed_resumes"])
        if done >= int(meta["total_resumes"]):
            try:
                self.table.update_item(
                    Key={"PK": keys.job_pk(job_id), "SK": keys.META_SK},
                    UpdateExpression="SET #s = :done, updated_at = :u",
                    ConditionExpression="#s <> :done",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={
                        ":done": JobStatus.COMPLETED.value,
                        ":u": utcnow_iso(),
                    },
                )
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                    raise

    # ── reads (results) ──────────────────────────────────────────────────
    def get_job_meta(self, job_id: str) -> Optional[dict]:
        resp = self.table.get_item(
            Key={"PK": keys.job_pk(job_id), "SK": keys.META_SK}
        )
        item = resp.get("Item")
        return _to_native(item) if item else None

    def get_job_results(self, job_id: str) -> Optional[JobResults]:
        resp = self.table.query(
            KeyConditionExpression=Key("PK").eq(keys.job_pk(job_id))
        )
        items = [_to_native(i) for i in resp.get("Items", [])]
        meta = next((i for i in items if i["SK"] == keys.META_SK), None)
        if meta is None:
            return None

        candidates = [
            CandidateResult(
                resume_id=i["resume_id"],
                file_name=i["file_name"],
                status=CandidateStatus(i["status"]),
                score=i.get("score"),
                summary=i.get("summary"),
                strengths=i.get("strengths", []),
                gaps=i.get("gaps", []),
                extracted=ExtractedFields(**i["extracted"]) if i.get("extracted") else None,
                error=i.get("error"),
            )
            for i in items
            if i.get("entity") == "CANDIDATE"
        ]
        # Rank is derived at read time: highest score first, scored before unscored.
        ranked = sorted(
            candidates,
            key=lambda c: (c.score is not None, c.score or 0),
            reverse=True,
        )
        for idx, c in enumerate(ranked, start=1):
            if c.status == CandidateStatus.SCORED:
                c.rank = idx

        return JobResults(
            job_id=meta["job_id"],
            title=meta["title"],
            status=JobStatus(meta["status"]),
            created_at=meta["created_at"],
            total_resumes=int(meta["total_resumes"]),
            processed_resumes=int(meta["processed_resumes"]),
            failed_resumes=int(meta["failed_resumes"]),
            candidates=ranked,
        )

    def list_jobs(self, limit: int = 50) -> List[JobSummary]:
        resp = self.table.query(
            IndexName=keys.GSI1_NAME,
            KeyConditionExpression=Key("GSI1PK").eq(keys.JOBS_GSI1PK),
            ScanIndexForward=False,
            Limit=limit,
        )
        return [
            JobSummary(
                job_id=i["job_id"],
                title=i["title"],
                status=JobStatus(i["status"]),
                created_at=i["created_at"],
                total_resumes=int(i["total_resumes"]),
                processed_resumes=int(i["processed_resumes"]),
                failed_resumes=int(i["failed_resumes"]),
            )
            for i in (_to_native(x) for x in resp.get("Items", []))
        ]
