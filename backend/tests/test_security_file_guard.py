from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.security import (
    FileOperationTimeoutError,
    FileQuotaExceededError,
    PathOutsideRootError,
    SecureFileGateway,
    SensitiveFileAccessError,
    UnsupportedFileTypeError,
)


def test_read_text_blocks_path_traversal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / "ok.md").write_text("hello", encoding="utf-8")
    (outside / "note.md").write_text("outside", encoding="utf-8")

    gateway = SecureFileGateway(root_path=workspace)

    assert gateway.read_text("ok.md") == "hello"
    with pytest.raises(PathOutsideRootError):
        gateway.read_text("../outside/note.md")


def test_read_text_blocks_sensitive_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".env").write_text("API_KEY=test", encoding="utf-8")
    (workspace / "secret-token.md").write_text("ignore", encoding="utf-8")

    gateway = SecureFileGateway(root_path=workspace)

    with pytest.raises(SensitiveFileAccessError):
        gateway.read_text(".env")
    with pytest.raises(SensitiveFileAccessError):
        gateway.read_text("secret-token.md")


def test_read_text_enforces_quota_and_type(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "big.md").write_text("a" * 200, encoding="utf-8")
    (workspace / "bin.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    gateway = SecureFileGateway(root_path=workspace, max_read_bytes=32)

    with pytest.raises(FileQuotaExceededError):
        gateway.read_text("big.md")
    with pytest.raises(UnsupportedFileTypeError):
        gateway.read_text("bin.png")


def test_read_text_enforces_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "slow.md"
    target.write_text("slow", encoding="utf-8")

    gateway = SecureFileGateway(root_path=workspace, timeout_seconds=0.01)

    def slow_read(path: Path, *, max_bytes: int) -> bytes:
        _ = (path, max_bytes)
        time.sleep(0.1)
        return b"slow"

    monkeypatch.setattr("app.security.file_guard._read_file_bytes_with_limit", slow_read)
    with pytest.raises(FileOperationTimeoutError):
        gateway.read_text("slow.md")
