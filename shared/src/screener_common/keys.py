"""Key conventions — the literal strings that couple the services together.

DynamoDB single-table design (table ``settings.ddb_table``):

    PK = "JOB#<jobId>"   SK = "META"             -> job metadata / status
    PK = "JOB#<jobId>"   SK = "CAND#<resumeId>"  -> one candidate result

    GSI1: GSI1PK = "JOBS"  GSI1SK = "<createdAt>" -> list jobs newest-first

S3 layout (bucket ``settings.s3_bucket``):

    jobs/<jobId>/jd/<fileName>
    jobs/<jobId>/resumes/<resumeId>/<fileName>
"""

from __future__ import annotations

# ── DynamoDB ────────────────────────────────────────────────────────────────
META_SK = "META"
GSI1_NAME = "GSI1"
JOBS_GSI1PK = "JOBS"


def job_pk(job_id: str) -> str:
    return f"JOB#{job_id}"


def candidate_sk(resume_id: str) -> str:
    return f"CAND#{resume_id}"


# ── S3 ──────────────────────────────────────────────────────────────────────
def jd_key(job_id: str, file_name: str) -> str:
    return f"jobs/{job_id}/jd/{file_name}"


def resume_key(job_id: str, resume_id: str, file_name: str) -> str:
    return f"jobs/{job_id}/resumes/{resume_id}/{file_name}"
