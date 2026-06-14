# Build context is the repo root (so we can copy the shared package).
#   docker build -f services/intake/Dockerfile -t intake .
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install the shared contract package first (changes least often).
COPY shared /opt/shared
RUN pip install /opt/shared

COPY services/intake/requirements.txt .
RUN pip install -r requirements.txt

COPY services/intake/app ./app

EXPOSE 8000

# Run as non-root.
RUN useradd -m appuser
USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
