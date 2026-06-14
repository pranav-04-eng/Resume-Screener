"""Results service entrypoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.controllers import jobs
from screener_common.logging_config import configure_logging

configure_logging("results")

app = FastAPI(title="Resume Screener — Results", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router)


@app.get("/healthz", tags=["health"])
def healthz() -> dict:
    return {"status": "ok"}
