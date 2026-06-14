"""Structured JSON logging used by every service.

Emits one JSON object per line so logs are queryable in CloudWatch Logs
Insights once running on EKS. ``configure_logging`` is idempotent and safe to
call at process start.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from screener_common.settings import settings

_RESERVED = set(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Promote any extra=... fields (e.g. job_id, resume_id) to top level.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(service: str) -> logging.Logger:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
    # Quiet noisy third-party loggers.
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logger = logging.getLogger(service)
    logger.info("logging configured", extra={"service": service, "runtime_env": settings.runtime_env})
    return logger
