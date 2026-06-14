"""Worker entrypoint — long-polls SQS and processes resumes.

Retry / DLQ semantics:
  * success                         -> delete message
  * failure, receiveCount < max     -> leave message (SQS makes it visible
                                        again after the visibility timeout)
  * failure, receiveCount >= max    -> mark candidate FAILED + delete; SQS's
                                        redrive policy routes it to the DLQ

This service has no HTTP surface; KEDA scales the Deployment on queue depth
(including to zero when the queue is empty).
"""

from __future__ import annotations

import signal
import sys

from app.services.processor import Processor
from screener_common.aws import sqs_client
from screener_common.logging_config import configure_logging
from screener_common.models import JobMessage
from screener_common.settings import settings

log = configure_logging("worker")

# Matches the maxReceiveCount in the queue's redrive policy.
MAX_RECEIVE = 3

_running = True


def _stop(signum, _frame):
    global _running
    log.info("shutdown signal received", extra={"signal": signum})
    _running = False


def run() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    sqs = sqs_client()
    processor = Processor()
    log.info("worker started", extra={"queue": settings.sqs_queue_url})

    while _running:
        resp = sqs.receive_message(
            QueueUrl=settings.sqs_queue_url,
            MaxNumberOfMessages=min(settings.worker_batch_size, 10),
            WaitTimeSeconds=settings.worker_poll_wait_seconds,
            AttributeNames=["ApproximateReceiveCount"],
        )
        for raw in resp.get("Messages", []):
            _handle(sqs, processor, raw)


def _handle(sqs, processor: Processor, raw: dict) -> None:
    receive_count = int(raw.get("Attributes", {}).get("ApproximateReceiveCount", "1"))
    try:
        msg = JobMessage.model_validate_json(raw["Body"])
    except Exception:
        log.exception("undecodable message; deleting")
        _delete(sqs, raw)
        return

    try:
        processor.process(msg)
        _delete(sqs, raw)
    except Exception as exc:  # noqa: BLE001
        if receive_count >= MAX_RECEIVE:
            log.error(
                "terminal failure; marking candidate failed",
                extra={"job_id": msg.job_id, "resume_id": msg.resume_id, "attempts": receive_count},
            )
            processor.mark_failed(msg, str(exc))
            _delete(sqs, raw)
        else:
            # Leave the message; it becomes visible again for another attempt.
            log.warning(
                "transient failure; will retry",
                extra={
                    "job_id": msg.job_id,
                    "resume_id": msg.resume_id,
                    "attempts": receive_count,
                    "error": str(exc),
                },
                exc_info=exc,
            )


def _delete(sqs, raw: dict) -> None:
    sqs.delete_message(QueueUrl=settings.sqs_queue_url, ReceiptHandle=raw["ReceiptHandle"])


if __name__ == "__main__":
    try:
        run()
    except Exception:
        log.exception("worker crashed")
        sys.exit(1)
