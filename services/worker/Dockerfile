# Build context is the repo root.
#   docker build -f services/worker/Dockerfile -t worker .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY shared /opt/shared
RUN pip install /opt/shared

COPY services/worker/requirements.txt .
RUN pip install -r requirements.txt

COPY services/worker/app ./app

RUN useradd -m appuser
USER appuser

CMD ["python", "-m", "app.main"]
