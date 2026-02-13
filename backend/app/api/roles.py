from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.api.errors import ApiException, error_response_docs
from app.db.models import Project
from app.db.session import get_session

router = APIRouter(prefix="/roles", tags=["roles"])

DbSession = Annotated[Session, Depends(get_session)]
_ROLES_STORE_FILE = ".beebeebrain_roles.json"


class RoleRead(BaseModel):
    id: str
    project_id: int
    name: str
    description: str
    checkpoint_preference: str
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class RoleCreateRequest(BaseModel):
    project_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    checkpoint_preference: str = Field(default="", max_length=500)
    tags: list[str] = Field(default_factory=list, max_length=32)


class RoleUpdateRequest(BaseModel):
    project_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    checkpoint_preference: str = Field(default="", max_length=500)
    tags: list[str] = Field(default_factory=list, max_length=32)


def _require_project(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise ApiException(
            status.HTTP_404_NOT_FOUND,
            "PROJECT_NOT_FOUND",
            f"Project {project_id} does not exist.",
        )
    return project


def _store_path(project_root: Path) -> Path:
    return project_root / _ROLES_STORE_FILE


def _load_roles(project_root: Path) -> list[RoleRead]:
    path = _store_path(project_root)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    roles: list[RoleRead] = []
    for item in payload:
        try:
            roles.append(RoleRead.model_validate(item))
        except Exception:
            continue
    return roles


def _save_roles(project_root: Path, roles: list[RoleRead]) -> None:
    path = _store_path(project_root)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    serialized = [role.model_dump(mode="json") for role in roles]
    temp_path.write_text(json.dumps(serialized, ensure_ascii=True, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _find_role_or_404(roles: list[RoleRead], role_id: str) -> int:
    for index, role in enumerate(roles):
        if role.id == role_id:
            return index
    raise ApiException(
        status.HTTP_404_NOT_FOUND,
        "ROLE_NOT_FOUND",
        f"Role {role_id} does not exist.",
    )


@router.get(
    "",
    response_model=list[RoleRead],
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(status.HTTP_422_UNPROCESSABLE_CONTENT, status.HTTP_404_NOT_FOUND),
    ),
)
def list_roles(
    session: DbSession,
    project_id: Annotated[int, Query(gt=0)],
) -> list[RoleRead]:
    project = _require_project(session, project_id)
    roles = _load_roles(Path(project.root_path).resolve())
    return [role for role in roles if role.project_id == project_id]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=RoleRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ),
    ),
)
def create_role(payload: RoleCreateRequest, session: DbSession) -> RoleRead:
    project = _require_project(session, payload.project_id)
    root = Path(project.root_path).resolve()
    roles = _load_roles(root)
    now = datetime.now(UTC)
    role = RoleRead(
        id=uuid4().hex,
        project_id=payload.project_id,
        name=payload.name.strip(),
        description=payload.description.strip(),
        checkpoint_preference=payload.checkpoint_preference.strip(),
        tags=[tag.strip() for tag in payload.tags if tag.strip()],
        created_at=now,
        updated_at=now,
    )
    roles.append(role)
    _save_roles(root, roles)
    return role


@router.put(
    "/{role_id}",
    response_model=RoleRead,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ),
    ),
)
def update_role(role_id: str, payload: RoleUpdateRequest, session: DbSession) -> RoleRead:
    project = _require_project(session, payload.project_id)
    root = Path(project.root_path).resolve()
    roles = _load_roles(root)
    role_index = _find_role_or_404(roles, role_id)
    existing = roles[role_index]
    if existing.project_id != payload.project_id:
        raise ApiException(
            status.HTTP_404_NOT_FOUND,
            "ROLE_NOT_FOUND",
            f"Role {role_id} does not exist in project {payload.project_id}.",
        )
    updated = RoleRead(
        id=existing.id,
        project_id=existing.project_id,
        name=payload.name.strip(),
        description=payload.description.strip(),
        checkpoint_preference=payload.checkpoint_preference.strip(),
        tags=[tag.strip() for tag in payload.tags if tag.strip()],
        created_at=existing.created_at,
        updated_at=datetime.now(UTC),
    )
    roles[role_index] = updated
    _save_roles(root, roles)
    return updated


@router.delete(
    "/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=cast(
        dict[int | str, dict[str, Any]],
        error_response_docs(
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ),
    ),
)
def delete_role(
    role_id: str,
    session: DbSession,
    project_id: Annotated[int, Query(gt=0)],
) -> None:
    project = _require_project(session, project_id)
    root = Path(project.root_path).resolve()
    roles = _load_roles(root)
    role_index = _find_role_or_404(roles, role_id)
    if roles[role_index].project_id != project_id:
        raise ApiException(
            status.HTTP_404_NOT_FOUND,
            "ROLE_NOT_FOUND",
            f"Role {role_id} does not exist in project {project_id}.",
        )
    roles.pop(role_index)
    _save_roles(root, roles)
