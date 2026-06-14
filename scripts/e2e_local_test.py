"""End-to-end backend smoke test against mocked AWS (moto).

Exercises the REAL intake service, shared repository and worker consumer loop
against in-process S3 + DynamoDB + SQS. The LLM pipeline is stubbed so the test
runs without a Groq key. Run:  python scripts/e2e_local_test.py
"""

import os
import sys

os.environ.update(
    RUNTIME_ENV="local",
    AWS_ENDPOINT_URL="",  # let moto intercept the default endpoints
    AWS_REGION="us-east-1",
    AWS_ACCESS_KEY_ID="test",
    AWS_SECRET_ACCESS_KEY="test",
    S3_BUCKET="resume-screener-files",
    DDB_TABLE="resume-screener",
    SQS_QUEUE_URL="",  # filled in after queue creation
)

import boto3
from moto import mock_aws

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_service(name):
    """Make ``import app.*`` resolve to one service at a time.

    Each service ships its own top-level ``app`` package — fine in separate
    containers, but they collide in one process, so we purge cached ``app``
    modules and re-prioritise the chosen service's directory.
    """
    for mod in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[mod]
    path = os.path.join(REPO_ROOT, "services", name)
    if path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)


FAILS = []


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        FAILS.append(name)


@mock_aws
def main():
    region = "us-east-1"
    # ── provision mocked AWS ────────────────────────────────────────────
    s3 = boto3.client("s3", region_name=region)
    s3.create_bucket(Bucket="resume-screener-files")

    ddb = boto3.client("dynamodb", region_name=region)
    ddb.create_table(
        TableName="resume-screener",
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
            {"AttributeName": "GSI1PK", "AttributeType": "S"},
            {"AttributeName": "GSI1SK", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "GSI1",
                "KeySchema": [
                    {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                    {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    sqs = boto3.client("sqs", region_name=region)
    queue_url = sqs.create_queue(QueueName="resume-screener-jobs")["QueueUrl"]
    os.environ["SQS_QUEUE_URL"] = queue_url

    # Reset cached settings/clients so they pick up the queue URL + moto.
    import screener_common.settings as settings_mod
    settings_mod.get_settings.cache_clear()
    settings_mod.settings = settings_mod.get_settings()
    import screener_common.aws as aws_mod
    for fn in (aws_mod.s3_client, aws_mod.sqs_client, aws_mod.dynamodb_resource):
        fn.cache_clear()

    # ── intake: create job ──────────────────────────────────────────────
    load_service("intake")
    from app.services.intake_service import IntakeService
    from screener_common.models import CreateJobRequest, ResumeUploadSpec, JobStatus

    intake = IntakeService()
    resp = intake.create_job(
        CreateJobRequest(
            title="Senior Backend Engineer",
            jd_file_name="jd.txt",
            resumes=[
                ResumeUploadSpec(file_name="alice.txt"),
                ResumeUploadSpec(file_name="bob.txt"),
            ],
        )
    )
    print(f"\n[intake] created job {resp.job_id}")
    check("job status CREATED", resp.status == JobStatus.CREATED)
    check("2 resume presigned URLs", len(resp.resume_uploads) == 2)
    check("jd presigned URL present", resp.jd_upload.upload_url.startswith("http"))

    # ── simulate browser uploads (direct to S3) ─────────────────────────
    s3.put_object(Bucket="resume-screener-files", Key=resp.jd_upload.key,
                  Body=b"Looking for a senior backend engineer with Python and AWS.")
    s3.put_object(Bucket="resume-screener-files", Key=resp.resume_uploads[0].key,
                  Body=b"Alice: 8 years Python, AWS, distributed systems.")
    s3.put_object(Bucket="resume-screener-files", Key=resp.resume_uploads[1].key,
                  Body=b"Bob: 1 year frontend React.")

    # ── intake: submit -> enqueue ───────────────────────────────────────
    intake.submit_job(resp.job_id)
    attrs = sqs.get_queue_attributes(QueueUrl=queue_url,
                                     AttributeNames=["ApproximateNumberOfMessages"])
    print(f"[intake] submitted; queue depth ~{attrs['Attributes']['ApproximateNumberOfMessages']}")

    from screener_common.repository import JobRepository
    repo = JobRepository()
    meta = repo.get_job_meta(resp.job_id)
    check("job status QUEUED after submit", meta["status"] == JobStatus.QUEUED.value)

    # ── worker: stub the LLM pipeline, then drain the queue ─────────────
    load_service("worker")
    import app.services.processor as proc_mod
    from screener_common.models import ExtractedFields, ScoreResult

    def fake_extract(text):
        return ExtractedFields(name="Alice" if "Alice" in text else "Bob",
                               skills=["python", "aws"] if "Python" in text else ["react"],
                               years_experience=8.0 if "Alice" in text else 1.0)

    def fake_score(jd, extracted, text):
        s = 92.0 if extracted.name == "Alice" else 35.0
        return ScoreResult(score=s, summary=f"{extracted.name} fit",
                           strengths=extracted.skills, gaps=[])

    proc_mod.extract_fields = fake_extract
    proc_mod.score_candidate = fake_score

    from app.services.processor import Processor
    import app.main as worker_main
    worker_main.settings = settings_mod.settings  # ensure queue url

    processor = Processor()
    drained = 0
    while True:
        r = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10,
                                WaitTimeSeconds=0, AttributeNames=["ApproximateReceiveCount"])
        msgs = r.get("Messages", [])
        if not msgs:
            break
        for raw in msgs:
            worker_main._handle(sqs, processor, raw)
            drained += 1
    print(f"[worker] processed {drained} messages")
    check("worker processed 2 resumes", drained == 2)

    # ── results: read back ranked output ────────────────────────────────
    load_service("results")
    from app.services.results_service import ResultsService  # noqa: E402
    from screener_common.models import CandidateStatus

    results = ResultsService().get_job(resp.job_id)
    print(f"[results] job status={results.status.value} "
          f"processed={results.processed_resumes}/{results.total_resumes}")
    check("job COMPLETED", results.status == JobStatus.COMPLETED)
    check("both candidates SCORED",
          all(c.status == CandidateStatus.SCORED for c in results.candidates))
    top = results.candidates[0]
    check("Alice ranked #1", top.rank == 1 and top.score == 92.0)
    check("ranks are 1,2", [c.rank for c in results.candidates] == [1, 2])

    print("\n[results] ranking:")
    for c in results.candidates:
        print(f"   #{c.rank}  {c.file_name:12s} score={c.score}  status={c.status.value}")

    # job listing via GSI
    jobs = ResultsService().list_jobs()
    check("job appears in list", any(j.job_id == resp.job_id for j in jobs))


if __name__ == "__main__":
    main()
    print()
    if FAILS:
        print(f"❌ {len(FAILS)} check(s) failed: {FAILS}")
        sys.exit(1)
    print("✅ All end-to-end checks passed.")
