# One-command local stack: LocalStack + intake + results + worker + frontend.
# Each service runs in its own window. Run from the repo root or anywhere:
#   powershell -ExecutionPolicy Bypass -File scripts/run-local.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Note($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

# --- prereqs ---------------------------------------------------------------
if (-not (Test-Path ".venv")) {
  Note "Creating .venv and installing backend deps (first run only)..."
  python -m venv .venv
  & ".venv\Scripts\python.exe" -m pip install -q -e shared `
    -r services/intake/requirements.txt `
    -r services/results/requirements.txt `
    -r services/worker/requirements.txt
}
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$Uvicorn = Join-Path $Root ".venv\Scripts\uvicorn.exe"

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Note "Created .env from example - set GROQ_API_KEY for scoring."
}

# Load .env into the current process environment.
Get-Content ".env" | Where-Object { $_ -match '^\s*[^#].*=' } | ForEach-Object {
  $k, $v = $_ -split '=', 2
  [Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim(), "Process")
}

# --- 1. LocalStack ---------------------------------------------------------
Note "Starting LocalStack..."
docker compose up -d localstack | Out-Null
for ($i = 0; $i -lt 30; $i++) {
  try { Invoke-WebRequest "http://localhost:4566/_localstack/health" -UseBasicParsing -TimeoutSec 2 | Out-Null; break }
  catch { Start-Sleep -Seconds 2 }
}
Note "LocalStack ready (S3 / DynamoDB / SQS)."

# --- 1b. Bootstrap LocalStack resources (idempotent) ----------------------
Note "Ensuring S3 / DynamoDB / SQS resources exist..."
$LS  = "http://localhost:4566"
$awsBase = @("--endpoint-url", $LS,
             "--region", "us-east-1",
             "--output", "text")
$env:AWS_ACCESS_KEY_ID     = "test"
$env:AWS_SECRET_ACCESS_KEY = "test"
$env:AWS_DEFAULT_REGION    = "us-east-1"

# S3 bucket
$buckets = aws @awsBase s3api list-buckets --query "Buckets[].Name" 2>$null
if ($buckets -notmatch "resume-screener-files") {
  aws @awsBase s3api create-bucket --bucket resume-screener-files | Out-Null
  $cors = '{"CORSRules":[{"AllowedHeaders":["*"],"AllowedMethods":["PUT","GET"],"AllowedOrigins":["*"],"ExposeHeaders":["ETag"]}]}'
  $cors | Set-Content -Encoding ascii "$env:TEMP\cors.json"
  aws @awsBase s3api put-bucket-cors --bucket resume-screener-files --cors-configuration "file://$env:TEMP\cors.json" | Out-Null
  Note "  Created S3 bucket resume-screener-files"
}

# DynamoDB table
$tables = aws @awsBase dynamodb list-tables --query "TableNames" 2>$null
if ($tables -notmatch "resume-screener") {
  aws @awsBase dynamodb create-table `
    --table-name resume-screener `
    --attribute-definitions AttributeName=PK,AttributeType=S AttributeName=SK,AttributeType=S AttributeName=GSI1PK,AttributeType=S AttributeName=GSI1SK,AttributeType=S `
    --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE `
    --global-secondary-indexes '[{"IndexName":"GSI1","KeySchema":[{"AttributeName":"GSI1PK","KeyType":"HASH"},{"AttributeName":"GSI1SK","KeyType":"RANGE"}],"Projection":{"ProjectionType":"ALL"}}]' `
    --billing-mode PAY_PER_REQUEST | Out-Null
  Note "  Created DynamoDB table resume-screener"
}

# SQS queues
$queues = aws @awsBase sqs list-queues --query "QueueUrls" 2>$null
if ($queues -notmatch "resume-screener-jobs-dlq") {
  aws @awsBase sqs create-queue --queue-name resume-screener-jobs-dlq | Out-Null
  Note "  Created SQS DLQ resume-screener-jobs-dlq"
}
if ($queues -notmatch "resume-screener-jobs`"") {
  $dlqUrl = aws @awsBase sqs get-queue-url --queue-name resume-screener-jobs-dlq --query QueueUrl 2>$null
  $dlqArn = aws @awsBase sqs get-queue-attributes --queue-url $dlqUrl --attribute-names QueueArn --query "Attributes.QueueArn" 2>$null
  $redrive = '{"deadLetterTargetArn":"' + $dlqArn + '","maxReceiveCount":"3"}'
  aws @awsBase sqs create-queue --queue-name resume-screener-jobs `
    --attributes "VisibilityTimeout=300" | Out-Null
  $mainUrl = aws @awsBase sqs get-queue-url --queue-name resume-screener-jobs --query QueueUrl 2>$null
  aws @awsBase sqs set-queue-attributes --queue-url $mainUrl `
    --attributes "RedrivePolicy=$redrive" | Out-Null
  Note "  Created SQS queue resume-screener-jobs"
}
Note "LocalStack resources ready."

# Helper: launch a command in a new PowerShell window with env inherited.
function Start-Svc($title, $command) {
  Note "Starting $title..."
  Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "`$host.UI.RawUI.WindowTitle='$title'; Set-Location '$Root'; $command"
  ) | Out-Null
}

# --- 2-4. backend services -------------------------------------------------
Start-Svc "intake"  "& '$Uvicorn' app.main:app --app-dir services/intake  --host 0.0.0.0 --port 8001"
Start-Svc "results" "& '$Uvicorn' app.main:app --app-dir services/results --host 0.0.0.0 --port 8002"
Start-Svc "worker"  "`$env:PYTHONPATH='services/worker'; & '$Py' -m app.main"

# --- 5. frontend -----------------------------------------------------------
if (-not (Test-Path "frontend/node_modules")) {
  Note "Installing frontend deps (first run only)..."
  Push-Location frontend; npm install | Out-Null; Pop-Location
}
if (-not (Test-Path "frontend/.env")) { Copy-Item "frontend/.env.example" "frontend/.env" }
Start-Svc "frontend" "Set-Location frontend; npm run dev"

Start-Sleep -Seconds 4
Write-Host ""
Note "Local stack is up:"
Write-Host "   Frontend : http://localhost:5173  (or 5174 if 5173 was taken)"
Write-Host "   Intake   : http://localhost:8001/healthz"
Write-Host "   Results  : http://localhost:8002/healthz"
Write-Host "   Stop     : close the service windows, then 'docker compose down'"
if (-not $env:GROQ_API_KEY) {
  Write-Host "   WARNING: GROQ_API_KEY is empty - set it in .env and restart the worker to enable scoring." -ForegroundColor Yellow
}
