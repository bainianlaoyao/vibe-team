from __future__ import annotations

import base64
import json
import mimetypes
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.api.errors import ApiException, error_response_docs
from app.db.models import Project
from app.db.session import get_session
from app.security.file_guard import SecureFileGateway
from app.security.types import (
    FileOperationTimeoutError,
    FileQuotaExceededError,
    PathOutsideRootError,
    SensitiveFileAccessError,
    UnsupportedFileTypeError,
)

router = APIRouter(prefix="/files", tags=["files"])

DbSession = Annotated[Session, Depends(get_session)]
_PERMISSION_STORE_FILE = ".beebeebrain_file_permissions.json"
_TEXT_EXTENSIONS = {
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
    ".ts",
    ".tsx",
    ".js",
    ".vue",
    ".html",
    ".css",
}


class FileNodeType(StrEnum):
    FILE = "file"
    FOLDER = "folder"


class FilePermission(StrEnum):
    READ = "read"
    WRITE = "write"
    NONE = "none"
    INHERIT = "inherit"


class FileNodeRead(BaseModel):
    id: str
    name: str
    path: str
    type: FileNodeType
    kind: str
    size_bytes: int | None = None
    modified_at: datetime | None = None
    owner: str = "system"
    permission: FilePermission
    children: list[FileNodeRead] = Field(default_factory=list)


class FilesTreeRead(BaseModel):
    project_id: int
    root: FileNodeRead
    permissions_updated_at: datetime | None = None


class FileContentRead(BaseModel):
    id: str
    path: str
    name: str
    permission: FilePermission
    content_type: str
    content: str | None
    truncated: bool = False


class FilePermissionUpdateRequest(BaseModel):
    project_id: int = Field(gt=0)
    permission: FilePermission
    recursive: bool = False


class FilePermissionRead(BaseModel):
    id: str
    path: str
    permission: FilePermission


def _require_project(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise ApiException(
            status.HTTP_404_NOT_FOUND,
            "PROJECT_NOT_FOUND",
            f"Project {project_id} does not exist.",
        )
    return project


def _encode_path(path: str) -> str:
    raw = path.encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_path(file_id: str) -> str:
    padding = "=" * (-len(file_id) % 4)
    try:
        raw = base64.urlsafe_b64decode(f"{file_id}{padding}".encode("ascii"))
        decoded = raw.decode("utf-8")
    except Exception as exc:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_FILE_ID",
            "file_id is not a valid encoded path.",
        ) from exc
    return decoded


def _normalize_relative(path: Path, *, root: Path) -> str:
    relative = path.relative_to(root).as_posix()
    return "." if relative in {"", "."} else relative


def _kind_for_path(path: Path) -> str:
    if path.is_dir():
        return "Folder"
    suffix = path.suffix.lower().lstrip(".")
    return suffix.upper() if suffix else "File"


def _load_permissions(project_root: Path) -> tuple[dict[str, FilePermission], datetime | None]:
    store_path = project_root / _PERMISSION_STORE_FILE
    if not store_path.exists():
        return {}, None
    try:
        payload = json.loads(store_path.read_text(encoding="utf-8"))
    except Exception:
        return {}, None
    raw_permissions = payload.get("permissions", {})
    if not isinstance(raw_permissions, dict):
        return {}, None
    permissions: dict[str, FilePermission] = {}
    for key, value in raw_permissions.items():
        try:
            permissions[str(key)] = FilePermission(str(value))
        except ValueError:
            continue
    modified_at = datetime.fromtimestamp(store_path.stat().st_mtime, tz=UTC)
    return permissions, modified_at


def _save_permissions(project_root: Path, permissions: dict[str, FilePermission]) -> datetime:
    store_path = project_root / _PERMISSION_STORE_FILE
    payload = {
        "version": 1,
        "permissions": {path: perm.value for path, perm in sorted(permissions.items())},
    }
    temp_path = store_path.with_suffix(f"{store_path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    temp_path.replace(store_path)
    return datetime.fromtimestamp(store_path.stat().st_mtime, tz=UTC)


def _effective_permission(
    relative_path: str,
    permissions: dict[str, FilePermission],
) -> FilePermission:
    normalized = "." if relative_path in {"", "."} else relative_path
    parts = [] if normalized == "." else normalized.split("/")
    candidates = ["."]
    current: list[str] = []
    for part in parts:
        current.append(part)
        candidates.append("/".join(current))
    for candidate in reversed(candidates):
        permission = permissions.get(candidate)
        if permission is not None:
            return permission
    return FilePermission.READ


def _build_tree_node(
    path: Path,
    *,
    root: Path,
    permissions: dict[str, FilePermission],
    max_depth: int,
    depth: int = 0,
) -> FileNodeRead:
    relative_path = _normalize_relative(path, root=root)
    node_type = FileNodeType.FOLDER if path.is_dir() else FileNodeType.FILE
    stat_result = path.stat()
    modified_at = datetime.fromtimestamp(stat_result.st_mtime, tz=UTC)
    size_bytes = None if path.is_dir() else stat_result.st_size
    children: list[FileNodeRead] = []
    if path.is_dir() and depth < max_depth:
        entries = sorted(path.iterdir(), key=lambda item: (item.is_file(), item.name.lower()))
        for child in entries:
            children.append(
                _build_tree_node(
                    child,
                    root=root,
                    permissions=permissions,
                    max_depth=max_depth,
                    depth=depth + 1,
                )
            )
    return FileNodeRead(
        id=_encode_path(relative_path),
        name=path.name if relative_path != "." else root.name,
        path=relative_path,
        type=node_type,
        kind=_kind_for_path(path),
        size_bytes=size_bytes,
        modified_at=modified_at,
        permission=_effective_permission(relative_path, permissions),
        children=children,
    )


def _resolve_target_path(
    project_root: Path,
    *,
    encoded_path: str | None = None,
    plain_path: str | None = None,
) -> Path:
    if plain_path is not None:
        candidate = plain_path
    elif encoded_path is not None:
        candidate = _decode_path(encoded_path)
    else:
        candidate = "."
    resolved = (project_root / candidate).resolve()
    if project_root not in resolved.parents and resolved != project_root:
        raise ApiException(
            status.HTTP_403_FORBIDDEN,
            "PATH_OUTSIDE_ROOT",
            "Requested path resolves outside project root.",
        )
    if not resolved.exists():
        raise ApiException(
            status.HTTP_404_NOT_FOUND,
            "FILE_NOT_FOUND",
            f"Path '{candidate}' does not exist in project workspace.",
        )
    return resolved


def _translate_gateway_error(exc: Exception) -> ApiException:
    if isinstance(exc, PathOutsideRootError):
        return ApiException(
            status.HTTP_403_FORBIDDEN,
            "PATH_OUTSIDE_ROOT",
            "Requested path resolves outside project root.",
        )
    if isinstance(exc, SensitiveFileAccessError):
        return ApiException(
            status.HTTP_403_FORBIDDEN,
            "SENSITIVE_FILE_BLOCKED",
            str(exc),
        )
    if isinstance(exc, FileQuotaExceededError):
        return ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "FILE_READ_QUOTA_EXCEEDED",
            str(exc),
        )
    if isinstance(exc, FileOperationTimeoutError):
        return ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "FILE_READ_TIMEOUT",
            str(exc),
        )
    if isinstance(exc, UnsupportedFileTypeError):
        return ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "UNSUPPORTED_FILE_TYPE",
            str(exc),
        )
    return ApiException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "FILE_READ_FAILED",
        str(exc),
    )


@router.get(
    "",
    response_model=FilesTreeRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ),
    ),
)
def get_files_tree(
    session: DbSession,
    project_id: Annotated[int, Query(gt=0)],
    path: Annotated[str, Query(max_length=1024)] = ".",
    max_depth: Annotated[int, Query(ge=1, le=8)] = 4,
) -> FilesTreeRead:
    project = _require_project(session, project_id)
    project_root = Path(project.root_path).resolve()
    target = _resolve_target_path(project_root, plain_path=path)
    permissions, updated_at = _load_permissions(project_root)
    root_node = _build_tree_node(
        target,
        root=project_root,
        permissions=permissions,
        max_depth=max_depth,
    )
    return FilesTreeRead(project_id=project_id, root=root_node, permissions_updated_at=updated_at)


@router.get(
    "/{file_id}",
    response_model=FileNodeRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ),
    ),
)
def get_file(
    file_id: str,
    session: DbSession,
    project_id: Annotated[int, Query(gt=0)],
) -> FileNodeRead:
    project = _require_project(session, project_id)
    project_root = Path(project.root_path).resolve()
    target = _resolve_target_path(project_root, encoded_path=file_id)
    permissions, _ = _load_permissions(project_root)
    return _build_tree_node(target, root=project_root, permissions=permissions, max_depth=1)


@router.get(
    "/{file_id}/content",
    response_model=FileContentRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            status.HTTP_403_FORBIDDEN,
        ),
    ),
)
def get_file_content(
    file_id: str,
    session: DbSession,
    project_id: Annotated[int, Query(gt=0)],
    max_bytes: Annotated[int, Query(ge=1, le=1_000_000)] = 64 * 1024,
) -> FileContentRead:
    project = _require_project(session, project_id)
    project_root = Path(project.root_path).resolve()
    target = _resolve_target_path(project_root, encoded_path=file_id)
    if target.is_dir():
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "FILE_IS_DIRECTORY",
            "Cannot fetch content for a directory path.",
        )
    permissions, _ = _load_permissions(project_root)
    relative = _normalize_relative(target, root=project_root)
    permission = _effective_permission(relative, permissions)
    if permission == FilePermission.NONE:
        raise ApiException(
            status.HTTP_403_FORBIDDEN,
            "FILE_ACCESS_DENIED",
            "Current effective permission denies access for this file.",
        )

    mime_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    if target.suffix.lower() not in _TEXT_EXTENSIONS:
        return FileContentRead(
            id=file_id,
            path=relative,
            name=target.name,
            permission=permission,
            content_type=mime_type,
            content=None,
            truncated=False,
        )

    gateway = SecureFileGateway(root_path=project_root, max_read_bytes=max_bytes)
    try:
        content = gateway.read_text(relative, max_read_bytes=max_bytes)
    except Exception as exc:
        raise _translate_gateway_error(exc) from exc
    return FileContentRead(
        id=file_id,
        path=relative,
        name=target.name,
        permission=permission,
        content_type=mime_type,
        content=content,
        truncated=False,
    )


@router.patch(
    "/{file_id}/permissions",
    response_model=FilePermissionRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ),
    ),
)
def update_file_permission(
    file_id: str,
    payload: FilePermissionUpdateRequest,
    session: DbSession,
) -> FilePermissionRead:
    project = _require_project(session, payload.project_id)
    project_root = Path(project.root_path).resolve()
    target = _resolve_target_path(project_root, encoded_path=file_id)
    relative = _normalize_relative(target, root=project_root)
    permissions, _ = _load_permissions(project_root)

    if payload.permission == FilePermission.INHERIT:
        permissions.pop(relative, None)
    else:
        permissions[relative] = payload.permission

    if payload.recursive and target.is_dir():
        for child in target.rglob("*"):
            child_relative = _normalize_relative(child, root=project_root)
            if payload.permission == FilePermission.INHERIT:
                permissions.pop(child_relative, None)
            else:
                permissions[child_relative] = payload.permission

    _save_permissions(project_root, permissions)
    effective = _effective_permission(relative, permissions)
    return FilePermissionRead(id=file_id, path=relative, permission=effective)
