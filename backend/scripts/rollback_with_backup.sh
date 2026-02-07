#!/usr/bin/env bash
set -euo pipefail

DB_PATH="${1:-./beebeebrain.db}"
DOWNGRADE_TARGET="${2:--1}"
SKIP_DOWNGRADE="${SKIP_DOWNGRADE:-0}"

if [[ ! -f "$DB_PATH" ]]; then
  echo "Database file not found: $DB_PATH" >&2
  exit 1
fi

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_PATH="${DB_PATH}.${TIMESTAMP}.bak"

cp "$DB_PATH" "$BACKUP_PATH"
echo "Database backup created: $BACKUP_PATH"

if [[ "$SKIP_DOWNGRADE" != "1" ]]; then
  echo "Running alembic downgrade target: $DOWNGRADE_TARGET"
  uv run alembic downgrade "$DOWNGRADE_TARGET"
fi

echo "Rollback flow finished."
