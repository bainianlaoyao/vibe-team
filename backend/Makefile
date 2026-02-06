.PHONY: sync lint format format-check type-check test quality ci pre-commit-install

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

quality: lint format-check type-check test

ci: quality

pre-commit-install:
	uv run pre-commit install
