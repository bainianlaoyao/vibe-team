from __future__ import annotations


class FileSecurityError(RuntimeError):
    """Base exception for secure file access violations."""


class PathOutsideRootError(FileSecurityError):
    """Raised when requested path escapes the configured root."""


class SensitiveFileAccessError(FileSecurityError):
    """Raised when requested path is considered sensitive."""


class FileQuotaExceededError(FileSecurityError):
    """Raised when read quota is exceeded."""


class UnsupportedFileTypeError(FileSecurityError):
    """Raised when file extension or content type is not allowed."""


class FileOperationTimeoutError(FileSecurityError):
    """Raised when file operation exceeds timeout."""
