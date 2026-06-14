"""AWS client factory.

A single place that constructs boto3 clients so the LocalStack-vs-real-AWS
switch lives in exactly one spot. In ``aws`` mode no credentials or endpoint
are passed — boto3 resolves them from the IRSA-injected web identity token.
"""

from __future__ import annotations

from functools import lru_cache

import boto3
from botocore.client import BaseClient
from botocore.config import Config

from screener_common.settings import settings

_BOTO_CONFIG = Config(retries={"max_attempts": 5, "mode": "standard"})


def _client(service: str) -> BaseClient:
    kwargs = {"region_name": settings.aws_region, "config": _BOTO_CONFIG}
    if settings.boto_endpoint_url:
        kwargs["endpoint_url"] = settings.boto_endpoint_url
    return boto3.client(service, **kwargs)


@lru_cache
def s3_client() -> BaseClient:
    return _client("s3")


@lru_cache
def s3_presign_client() -> BaseClient:
    """S3 client whose endpoint is the browser-reachable one (see settings).

    Used only to generate pre-signed URLs; all other S3 I/O uses s3_client().
    """
    kwargs = {"region_name": settings.aws_region, "config": _BOTO_CONFIG}
    if settings.presign_endpoint_url:
        kwargs["endpoint_url"] = settings.presign_endpoint_url
    return boto3.client("s3", **kwargs)


@lru_cache
def sqs_client() -> BaseClient:
    return _client("sqs")


@lru_cache
def dynamodb_resource():
    kwargs = {"region_name": settings.aws_region, "config": _BOTO_CONFIG}
    if settings.boto_endpoint_url:
        kwargs["endpoint_url"] = settings.boto_endpoint_url
    return boto3.resource("dynamodb", **kwargs)


def jobs_table():
    return dynamodb_resource().Table(settings.ddb_table)
