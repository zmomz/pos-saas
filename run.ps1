# POS — build the frontend and run the whole app from a single uvicorn process.
#
# Usage:  ./run.ps1                (build frontend if needed, then serve)
#         ./run.ps1 -Rebuild       (force a fresh frontend build)
#         ./run.ps1 -Port 9000     (serve on a different port; default 8000)
#         ./run.ps1 -ApiOnly       (skip the frontend; serve the API only)
#         ./run.ps1 -Migrate       (use the Alembic migration chain instead of create_all)
#
# Requires: backend/.env configured (see backend/.env.example), Python deps
# installed (pip install -r backend/requirements.txt), Node + pnpm for the build.
#
# The backend serves the built SPA from frontend/dist, so the API and the UI
# share one origin/port — open http://localhost:8000 once it's up.
#
# Why this script loads .env itself: the app reads its config from real
# environment variables (core/config.py) and only auto-loads a .env file when
# run under a debugger. So `python -m uvicorn` would otherwise start with the
# insecure default JWT secret and NO admin account seeded. We load backend/.env
# into this process so ADMIN_*, JWT_SECRET_KEY, DATABASE_URL, etc. take effect.
#
# Why create_all by default: the local SQLite deploy builds its schema at
# runtime via create_all (see CLAUDE.md / RUN.md). The Alembic migration chain
# targets managed (Postgres) production; pass -Migrate to opt into it.

param(
    [switch]$Rebuild,
    [switch]$ApiOnly,
    [switch]$Migrate,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# 0. backend/.env must exist (JWT_SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD, ...).
$envFile = Join-Path $root "backend\.env"
if (-not (Test-Path $envFile)) {
    Write-Host "backend/.env is missing." -ForegroundColor Red
    Write-Host "Create it first:  Copy-Item backend\.env.example backend\.env  (then set JWT_SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD)" -ForegroundColor Yellow
    exit 1
}

# 1. Build the frontend if dist/ is missing or a rebuild was requested.
if (-not $ApiOnly) {
    $dist = Join-Path $root "frontend\dist"
    if ($Rebuild -or -not (Test-Path (Join-Path $dist "index.html"))) {
        Write-Host "Building frontend..." -ForegroundColor Cyan
        Push-Location (Join-Path $root "frontend")
        try {
            if (-not (Test-Path "node_modules")) { pnpm install }
            pnpm run build
        } finally {
            Pop-Location
        }
    } else {
        Write-Host "Using existing frontend build (pass -Rebuild to refresh)." -ForegroundColor DarkGray
    }
}

# 2. Load backend/.env into this process so the app's settings take effect.
Write-Host "Loading backend/.env ..." -ForegroundColor Cyan
Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
        $idx = $line.IndexOf('=')
        $key = $line.Substring(0, $idx).Trim()
        $val = $line.Substring($idx + 1).Trim()
        # Strip surrounding quotes if present.
        if ($val.Length -ge 2 -and (($val[0] -eq '"' -and $val[-1] -eq '"') -or ($val[0] -eq "'" -and $val[-1] -eq "'"))) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        if ($key) { Set-Item -Path "Env:$key" -Value $val }
    }
}

# Local default: build the schema with create_all (reliable for the SQLite
# single-process run). -Migrate opts into the Alembic chain (production path).
if ($Migrate) {
    $env:RUN_MIGRATIONS_ON_BOOT = "true"
    Write-Host "Schema: Alembic migration chain (-Migrate)." -ForegroundColor DarkGray
} else {
    $env:RUN_MIGRATIONS_ON_BOOT = "false"
    Write-Host "Schema: create_all (pass -Migrate to use Alembic migrations)." -ForegroundColor DarkGray
}

# 3. Start the backend. With a build present it serves the API *and* the SPA on
#    one port; with -ApiOnly (or no build) it serves the API alone.
Write-Host "Starting POS on http://localhost:$Port ..." -ForegroundColor Green
Push-Location (Join-Path $root "backend")
try {
    python -m uvicorn main:app --host 0.0.0.0 --port $Port
} finally {
    Pop-Location
}
