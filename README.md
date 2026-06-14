# Resume / Candidate Screener

Microservices app that lets recruiters upload a job description and a batch of
resumes, scores & ranks each candidate against the JD with an LLM (Groq via
LangChain), and returns structured, ranked results.

## Architecture

```
                 Route 53 ──► ALB (ACM TLS) ──► Ingress
                                                  │
        ┌─────────────────────┬───────────────────┼────────────────────┐
        ▼                     ▼                    ▼                    ▼
   frontend (React)      intake (FastAPI)    results (FastAPI)    [worker pods]
                              │                    ▲                    ▲
            presigned PUT     │  enqueue           │ read              │ consume
   browser ───────► S3        ▼                    │                   │
                          SQS (+DLQ) ──────────────┼───────────────────┘
                              │                     │
                              └──► DynamoDB ◄────────┘   (worker writes results)

   Worker: SQS → S3 read → LangChain/Groq extract→score → DynamoDB write
           scales on queue depth via KEDA (incl. to zero).
   Pods authenticate to AWS via IRSA (no static credentials).
```

| Service     | Role                                                            | Port |
|-------------|-----------------------------------------------------------------|------|
| `intake`    | presigned upload URLs, job records, enqueue to SQS              | 8001 |
| `results`   | job status + ranked candidate results (read API)               | 8002 |
| `worker`    | SQS consumer, LangChain→Groq extract/score, writes DynamoDB     | —    |
| `frontend`  | React app: create job, upload, view rankings                    | 5173 |

`shared/screener_common` is the contract package every service imports:
data models, status enums, S3/DynamoDB key conventions, the SQS message
schema, settings, structured logging and the DynamoDB repository.

## Local development

Everything runs against **LocalStack** (S3 + DynamoDB + SQS) — no AWS account
needed until you're ready to deploy.

```bash
cp .env.example .env          # set GROQ_API_KEY for the worker
docker compose up --build     # localstack + intake + results + worker
# resources are auto-created by scripts/init-localstack.sh on startup
```

Then run the frontend:

```bash
cd frontend && npm install && npm run dev
```

To run a single service on the host instead of in compose:

```bash
pip install -e shared -e services/intake
RUNTIME_ENV=local uvicorn app.main:app --app-dir services/intake --reload --port 8001
```

## Layout

```
shared/screener_common   # cross-service contracts (models, repo, settings, aws, logging)
services/intake          # FastAPI (MVC)
services/results         # FastAPI (MVC)
services/worker          # SQS consumer + LangChain/Groq pipeline
frontend                 # React + Vite + TS
k8s                      # Deployments, Services, Ingress, KEDA ScaledObject
infra                    # Terraform: VPC, EKS, ECR, S3, DynamoDB, SQS, IRSA, ACM, Route53
scripts                  # local bootstrap + ECR build/push
```

Build order & design notes live in [docs/architecture.md](docs/architecture.md).
