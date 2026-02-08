param(
    [int]$ProjectId = 2,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5175
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"

$allowedOrigins = @(
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5175",
    "http://127.0.0.1:5175",
    "http://localhost:$FrontendPort",
    "http://127.0.0.1:$FrontendPort"
) | Select-Object -Unique

$corsAllowOrigins = [string]::Join(",", $allowedOrigins)
$apiBaseUrl = "http://127.0.0.1:$BackendPort/api/v1"

$backendCmd = @"
cd '$backendDir'
`$env:APP_ENV='development'
`$env:CORS_ALLOW_ORIGINS='$corsAllowOrigins'
uv run uvicorn app.main:app --host 127.0.0.1 --port $BackendPort --reload
"@

$frontendCmd = @"
cd '$frontendDir'
`$env:VITE_PROJECT_ID='$ProjectId'
`$env:VITE_API_BASE_URL='$apiBaseUrl'
npm run dev -- --host 127.0.0.1 --port $FrontendPort --strictPort
"@

Start-Process -FilePath "powershell" -ArgumentList @("-NoExit", "-Command", $backendCmd) -WindowStyle Normal
Start-Sleep -Seconds 1
Start-Process -FilePath "powershell" -ArgumentList @("-NoExit", "-Command", $frontendCmd) -WindowStyle Normal

Write-Host "Backend:  http://127.0.0.1:$BackendPort"
Write-Host "Frontend: http://127.0.0.1:$FrontendPort"
Write-Host "ProjectId: $ProjectId"
