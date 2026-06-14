"""Shared LangChain/Groq LLM instance.

Built once per process and reused across messages. Groq gives fast inference;
LangChain's ``with_structured_output`` forces the model to return our Pydantic
models directly (no brittle JSON parsing).
"""

from __future__ import annotations

from functools import lru_cache

from langchain_groq import ChatGroq

from screener_common.settings import settings


@lru_cache
def get_llm() -> ChatGroq:
    return ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=0,
        max_retries=3,
    )
