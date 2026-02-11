#!/usr/bin/env bash
set -euo pipefail

export APP_ENV="${APP_ENV:-development}"
export PROJECT_ROOT="${PROJECT_ROOT:-../play_ground}"
echo "Starting BeeBeeBrain Backend..."
echo "Project root: $PROJECT_ROOT"
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
