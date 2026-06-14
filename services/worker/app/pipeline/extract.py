"""Stage 1 — extract structured fields from raw resume text."""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from app.pipeline.llm import get_llm
from screener_common.models import ExtractedFields

_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an expert resume parser. Extract the candidate's structured "
            "fields from the resume text. Only include information actually present; "
            "leave a field null/empty if it is not stated. Estimate years_experience "
            "as a number when it can be reasonably inferred from the work history.",
        ),
        ("human", "Resume text:\n\n{resume_text}"),
    ]
)


def extract_fields(resume_text: str) -> ExtractedFields:
    chain = _PROMPT | get_llm().with_structured_output(ExtractedFields)
    return chain.invoke({"resume_text": resume_text[:20000]})
