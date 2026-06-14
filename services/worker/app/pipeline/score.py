"""Stage 2 — score a candidate against the job description (absolute 0-100).

Ranking across the batch is derived at read time in the results service, so
scoring only needs an absolute, per-candidate judgement here.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from app.pipeline.llm import get_llm
from screener_common.models import ExtractedFields, ScoreResult

_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an expert technical recruiter. Score how well the candidate "
            "matches the job description on a 0-100 scale, where 100 is an ideal "
            "fit. Be calibrated and evidence-based: weigh required skills, years of "
            "relevant experience, and domain fit. Provide a concise summary, the "
            "candidate's key strengths relative to this role, and notable gaps.",
        ),
        (
            "human",
            "JOB DESCRIPTION:\n{jd_text}\n\n"
            "CANDIDATE (extracted fields):\n{candidate}\n\n"
            "CANDIDATE RESUME TEXT:\n{resume_text}",
        ),
    ]
)


def score_candidate(
    jd_text: str, extracted: ExtractedFields, resume_text: str
) -> ScoreResult:
    chain = _PROMPT | get_llm().with_structured_output(ScoreResult)
    return chain.invoke(
        {
            "jd_text": jd_text[:15000],
            "candidate": extracted.model_dump_json(indent=2),
            "resume_text": resume_text[:15000],
        }
    )
