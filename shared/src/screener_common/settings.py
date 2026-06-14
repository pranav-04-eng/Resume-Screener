"""Centralised, environment-driven configuration shared by all services.

The same code runs locally (against LocalStack) and in AWS (EKS via IRSA).
The only switch is ``RUNTIME_ENV``:

* ``local`` -> ``AWS_ENDPOINT_URL`` is honoured so boto3 talks to LocalStack.
* ``aws``   -> no endpoint override; the SDK uses real AWS endpoints and the
              IRSA-provided credentials. Never set static keys in this mode.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    runtime_env: Literal["local", "aws"] = "local"

    # AWS / endpoint
    aws_region: str = "us-east-1"
    aws_endpoint_url: Optional[str] = None  # only used when runtime_env == "local"
    # Endpoint the *browser* uses for pre-signed S3 PUTs. Locally this must be
    # reachable from the host (e.g. http://localhost:4566) even when the
    # service itself talks to LocalStack via a container hostname. Leave unset
    # in AWS so real S3 endpoints are used.
    s3_public_endpoint: Optional[str] = None

    # Resource names
    s3_bucket: str = "resume-screener-files"
    ddb_table: str = "resume-screener"
    sqs_queue_url: str = ""
    sqs_dlq_url: str = ""

    presign_expiry: int = 900

    # Worker / LLM
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    worker_poll_wait_seconds: int = 20
    worker_batch_size: int = 5

    log_level: str = "INFO"

    @property
    def is_local(self) -> bool:
        return self.runtime_env == "local"

    @property
    def boto_endpoint_url(self) -> Optional[str]:
        """Endpoint override for boto3 — only set in local mode."""
        return self.aws_endpoint_url if self.is_local else None

    @property
    def presign_endpoint_url(self) -> Optional[str]:
        """Endpoint used when generating pre-signed URLs for the browser.

        Falls back to the regular boto endpoint when not separately configured.
        """
        if self.s3_public_endpoint:
            return self.s3_public_endpoint
        return self.boto_endpoint_url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
