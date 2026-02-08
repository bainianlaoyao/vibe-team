.PHONY: sync lint format format-check type-check test api-probe failure-recovery-probe freeze-gate quality ci pre-commit-install

sync:
	uv sync --dev

lint:
	uv run ruff check .

format:
	uv run black .

format-check:
	uv run black --check .

type-check:
	uv run mypy app tests

test:
	uv run pytest

api-probe:
	uv run python scripts/api_probe.py --fail-on-error

failure-recovery-probe:
	uv run python scripts/failure_recovery_probe.py --fail-on-error

freeze-gate: api-probe failure-recovery-probe

quality: lint format-check type-check test

ci: quality

pre-commit-install:
	uv run pre-commit install
