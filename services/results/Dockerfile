# Build context is the repo root.
#   docker build -f services/results/Dockerfile -t results .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY shared /opt/shared
RUN pip install /opt/shared

COPY services/results/requirements.txt .
RUN pip install -r requirements.txt

COPY services/results/app ./app

EXPOSE 8000
RUN useradd -m appuser
USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
