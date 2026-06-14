"""Shared contracts and infrastructure helpers for Resume Screener services.

This package is the single source of truth for anything that couples the
intake, worker and results services together: the DynamoDB item shapes, the
job/candidate status state machine, S3 key conventions, the SQS message
schema, settings, structured logging and the AWS client factory.

Import submodules directly, e.g. ``from screener_common.settings import settings``.
We deliberately do NOT re-export ``settings`` from the package root: binding an
instance named ``settings`` here would shadow the ``screener_common.settings``
submodule and break ``import screener_common.settings``.
"""
