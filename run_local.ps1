param(
    [string]$DatabaseUrl = "postgresql+psycopg://postgres:postgres@localhost:5432/youtube_recs",
    [string]$RedisUrl = "redis://localhost:6379/0",
    [string]$CorsOrigins = "*",
    [ValidateSet("true", "false")]
    [string]$EnableTakeoutImport = "true",
    [ValidateSet("true", "false")]
    [string]$EnableSelfRestart = "false",
    [string]$SelfRestartToken = "",
    [double]$SelfRestartDelaySeconds = 0.6,
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$SkipCompose,
    [switch]$SkipInstall,
    [switch]$NoReload,
    [switch]$NoRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".\requirements.txt")) {
    throw "requirements.txt not found. Run this script from the project root."
}
if (-not (Test-Path ".\app\main.py")) {
    throw "app/main.py not found. Run this script from the project root."
}

function Write-Step {
    param([string]$Message)
    Write-Host "[run_local] $Message" -ForegroundColor Cyan
}

if (-not $SkipCompose) {
    Write-Step "Starting Postgres + Redis with docker-compose..."
    docker-compose up -d
}

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Step "Creating virtual environment (.venv)..."
    python -m venv .venv
}

Write-Step "Activating .venv..."
. "$PSScriptRoot\.venv\Scripts\Activate.ps1"

if (-not $SkipInstall) {
    Write-Step "Upgrading pip..."
    python -m pip install --upgrade pip
    Write-Step "Installing dependencies..."
    pip install -r requirements.txt
}

$env:DATABASE_URL = $DatabaseUrl
$env:REDIS_URL = $RedisUrl
$env:CORS_ORIGINS = $CorsOrigins
$env:ENABLE_TAKEOUT_IMPORT = $EnableTakeoutImport.ToLowerInvariant()
$env:ENABLE_SELF_RESTART = $EnableSelfRestart.ToLowerInvariant()
$env:SELF_RESTART_TOKEN = $SelfRestartToken
$env:SELF_RESTART_DELAY_SECONDS = [string]$SelfRestartDelaySeconds

Write-Step "Environment configured:"
Write-Host "  DATABASE_URL=$($env:DATABASE_URL)"
Write-Host "  REDIS_URL=$($env:REDIS_URL)"
Write-Host "  CORS_ORIGINS=$($env:CORS_ORIGINS)"
Write-Host "  ENABLE_TAKEOUT_IMPORT=$($env:ENABLE_TAKEOUT_IMPORT)"
Write-Host "  ENABLE_SELF_RESTART=$($env:ENABLE_SELF_RESTART)"
if ([string]::IsNullOrWhiteSpace($env:SELF_RESTART_TOKEN)) {
    Write-Host "  SELF_RESTART_TOKEN=<empty>"
} else {
    Write-Host "  SELF_RESTART_TOKEN=<set>"
}
Write-Host "  SELF_RESTART_DELAY_SECONDS=$($env:SELF_RESTART_DELAY_SECONDS)"

if ($NoRun) {
    Write-Step "Setup complete (NoRun enabled)."
    Write-Host "Start API manually with:"
    Write-Host "  uvicorn app.main:app --host $BindHost --port $Port"
    exit 0
}

if ($NoReload) {
    Write-Step "Starting API..."
    uvicorn app.main:app --host $BindHost --port $Port
} else {
    Write-Step "Starting API with --reload..."
    uvicorn app.main:app --reload --host $BindHost --port $Port
}
