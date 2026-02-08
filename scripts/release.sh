#!/usr/bin/env bash

set -euo pipefail

usage() {
  echo "Usage: scripts/release.sh <version>"
  echo "Example: scripts/release.sh 0.1.0"
}

if [[ $# -ne 1 ]]; then
  usage
  exit 1
fi

VERSION="$1"
TAG="v${VERSION}"

if [[ ! "${VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Invalid version: ${VERSION}. Expected semantic version format X.Y.Z."
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Working tree is not clean. Commit or stash changes before release."
  exit 1
fi

if git rev-parse "${TAG}" >/dev/null 2>&1; then
  echo "Tag ${TAG} already exists."
  exit 1
fi

echo "[release] updating backend version -> ${VERSION}"
sed -i.bak -E "0,/^version = \".*\"/s//version = \"${VERSION}\"/" backend/pyproject.toml
rm -f backend/pyproject.toml.bak

echo "[release] updating frontend version -> ${VERSION}"
npm --prefix frontend version "${VERSION}" --no-git-tag-version

if ! grep -q "## \\[${VERSION}\\]" CHANGELOG.md; then
  release_date="$(date +%Y-%m-%d)"
  {
    echo ""
    echo "## [${VERSION}] - ${release_date}"
    echo ""
    echo "- MVP release scope freeze."
  } >> CHANGELOG.md
fi

echo "[release] running backend quality gates"
(
  cd backend
  uv run ruff check .
  uv run black --check .
  uv run mypy app tests
  uv run pytest
)

echo "[release] running frontend build"
(
  cd frontend
  npm ci
  npm run build
)

git add backend/pyproject.toml frontend/package.json frontend/package-lock.json CHANGELOG.md
git commit -m "chore(release): ${TAG}"
git tag -a "${TAG}" -m "BeeBeeBrain MVP ${TAG}"

echo "[release] done: created commit and tag ${TAG}"
