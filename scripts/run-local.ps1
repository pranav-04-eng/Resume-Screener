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
