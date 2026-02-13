from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def _normalize_path(path: str) -> str:
    return str(Path(path).resolve()).rstrip("\\/").lower()


def test_start_backend_bat_avoids_hardcoded_machine_path() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "start-backend.bat"
    content = script.read_text(encoding="utf-8").lower()

    assert "%~dp0" in content
    assert "e:\\beebeebrain" not in content


@pytest.mark.skipif(sys.platform != "win32", reason="Windows batch script only")
def test_start_backend_bat_prints_backend_workdir(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "start-backend.bat"
    expected_backend_dir = repo_root / "backend"
    invoker_dir = tmp_path / "invoker"
    invoker_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["cmd", "/c", str(script), "--print-cwd"],
        cwd=invoker_dir,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    actual_path = result.stdout.strip().splitlines()[-1]
    assert _normalize_path(actual_path) == _normalize_path(str(expected_backend_dir))


@pytest.mark.skipif(sys.platform != "win32", reason="Windows batch script only")
def test_backend_start_backend_bat_delegates_to_root_script(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "backend" / "start_backend.bat"
    expected_backend_dir = repo_root / "backend"
    invoker_dir = tmp_path / "invoker"
    invoker_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["cmd", "/c", str(script), "--print-cwd"],
        cwd=invoker_dir,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    actual_path = result.stdout.strip().splitlines()[-1]
    assert _normalize_path(actual_path) == _normalize_path(str(expected_backend_dir))
