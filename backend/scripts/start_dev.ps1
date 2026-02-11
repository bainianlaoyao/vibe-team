$env:APP_ENV = "development"
$env:PROJECT_ROOT = "../play_ground"
Write-Host "Starting BeeBeeBrain Backend..."
Write-Host "Project root: $env:PROJECT_ROOT"
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
