from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Final

from app.core.logging import get_logger
from app.security.types import (
    FileOperationTimeoutError,
    FileQuotaExceededError,
    PathOutsideRootError,
    SensitiveFileAccessError,
    UnsupportedFileTypeError,
)

DEFAULT_MAX_READ_BYTES: Final[int] = 64 * 1024
DEFAULT_TIMEOUT_SECONDS: Final[float] = 1.5
DEFAULT_ALLOWED_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {
        ".md",
        ".txt",
        ".py",
        ".toml",
        ".yaml",
        ".yml",
        ".json",
        ".ini",
        ".cfg",
        ".sql",
        ".csv",
    }
)
_SENSITIVE_FILE_NAMES: Final[frozenset[str]] = frozenset(
    {
        ".env",
        ".env.local",
        ".env.development",
        ".env.test",
        ".env.production",
        "id_rsa",
        "id_ed25519",
    }
)
_SENSITIVE_SUFFIXES: Final[tuple[str, ...]] = (".pem", ".key", ".p12", ".pfx")
logger = get_logger("bbb.security.file_guard")


def _read_file_bytes_with_limit(path: Path, *, max_bytes: int) -> bytes:
    with path.open("rb") as file_obj:
        data = file_obj.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise FileQuotaExceededError(
            f"File read exceeds quota: {len(data)} bytes > max_bytes={max_bytes}."
        )
    return data


class SecureFileGateway:
    def __init__(
        self,
        *,
        root_path: str | Path,
        max_read_bytes: int = DEFAULT_MAX_READ_BYTES,
        allowed_extensions: set[str] | frozenset[str] | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if max_read_bytes <= 0:
            raise ValueError("max_read_bytes must be greater than 0")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0")
        self._root = Path(root_path).resolve()
        self._max_read_bytes = max_read_bytes
        self._allowed_extensions = frozenset(
            ext.lower() for ext in (allowed_extensions or DEFAULT_ALLOWED_EXTENSIONS)
        )
        self._timeout_seconds = timeout_seconds

    @property
    def root_path(self) -> Path:
        return self._root

    def read_text(
        self,
        path: str | Path,
        *,
        max_read_bytes: int | None = None,
        timeout_seconds: float | None = None,
    ) -> str:
        target = self.resolve_path(path)
        self._ensure_not_sensitive(target)
        self._ensure_supported_text_file(target)
        if not target.is_file():
            raise FileNotFoundError(f"File does not exist: {target}")

        resolved_max_bytes = max_read_bytes or self._max_read_bytes
        resolved_timeout = timeout_seconds or self._timeout_seconds
        if resolved_max_bytes <= 0:
            raise ValueError("max_read_bytes must be greater than 0")
        if resolved_timeout <= 0:
            raise ValueError("timeout_seconds must be greater than 0")

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    _read_file_bytes_with_limit,
                    target,
                    max_bytes=resolved_max_bytes,
                )
                raw = future.result(timeout=resolved_timeout)
        except FutureTimeoutError as exc:
            logger.warning(
                "security.file_read.timeout",
                path=target.name,
                timeout_seconds=resolved_timeout,
            )
            raise FileOperationTimeoutError(
                f"Timed out after {resolved_timeout:.3f}s while reading {target.name}."
            ) from exc

        if b"\x00" in raw:
            logger.warning("security.file_read.binary_blocked", path=target.name)
            raise UnsupportedFileTypeError(f"Binary content is not allowed: {target.name}")

        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UnsupportedFileTypeError(
                f"Only UTF-8 text files are supported: {target.name}"
            ) from exc

    def resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        combined = candidate if candidate.is_absolute() else self._root / candidate
        resolved = combined.resolve()
        if not _is_sub_path(path=resolved, root=self._root):
            logger.warning(
                "security.file_read.outside_root",
                path=str(path),
                root=self._root.as_posix(),
            )
            raise PathOutsideRootError(
                f"Path '{path}' resolves outside root '{self._root.as_posix()}'."
            )
        return resolved

    def _ensure_supported_text_file(self, path: Path) -> None:
        suffix = path.suffix.lower()
        if suffix not in self._allowed_extensions:
            logger.warning(
                "security.file_read.unsupported_extension",
                path=path.name,
                extension=suffix or "<none>",
            )
            raise UnsupportedFileTypeError(
                f"File extension '{suffix or '<none>'}' is not in the allowed whitelist."
            )

    def _ensure_not_sensitive(self, path: Path) -> None:
        lower_name = path.name.lower()
        if lower_name in _SENSITIVE_FILE_NAMES:
            logger.warning("security.file_read.sensitive_blocked", path=path.name)
            raise SensitiveFileAccessError(f"Access denied for sensitive file: {path.name}")
        if lower_name.endswith(_SENSITIVE_SUFFIXES):
            logger.warning("security.file_read.sensitive_blocked", path=path.name)
            raise SensitiveFileAccessError(f"Access denied for sensitive file: {path.name}")
        if "secret" in lower_name or "token" in lower_name:
            logger.warning("security.file_read.sensitive_blocked", path=path.name)
            raise SensitiveFileAccessError(f"Access denied for sensitive file: {path.name}")


def _is_sub_path(*, path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
