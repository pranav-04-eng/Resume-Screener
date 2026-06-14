"""Pull plain text out of resume/JD files (PDF, DOCX, TXT)."""

from __future__ import annotations

import io
import logging

log = logging.getLogger("worker.text")


def extract_text(file_name: str, data: bytes) -> str:
    name = file_name.lower()
    try:
        if name.endswith(".pdf"):
            return _from_pdf(data)
        if name.endswith(".docx"):
            return _from_docx(data)
    except Exception:  # noqa: BLE001 - fall back to best-effort decode
        log.warning("structured extraction failed; decoding as text", extra={"file": file_name})
    return data.decode("utf-8", errors="ignore")


def _from_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _from_docx(data: bytes) -> str:
    import docx

    document = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in document.paragraphs)
