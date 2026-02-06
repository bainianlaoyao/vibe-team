from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar, cast

from sqlalchemy import func, select
from sqlalchemy.sql import Select
from sqlmodel import Session

T = TypeVar("T")


class OptimisticLockError(RuntimeError):
    """Raised when versioned updates do not match the expected row version."""


@dataclass(frozen=True, slots=True)
class Pagination:
    page: int = 1
    page_size: int = 20

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("page must be >= 1")
        if self.page_size < 1:
            raise ValueError("page_size must be >= 1")
        if self.page_size > 100:
            raise ValueError("page_size must be <= 100")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


@dataclass(frozen=True, slots=True)
class Page(Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


def paginate(session: Session, statement: Select[Any], *, pagination: Pagination) -> Page[T]:
    count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
    count_row = session.exec(cast(Any, count_statement)).one()
    count_value = count_row[0] if hasattr(count_row, "__getitem__") else count_row
    total = int(count_value)
    paged_statement = statement.offset(pagination.offset).limit(pagination.page_size)
    rows = cast(list[T], list(session.exec(cast(Any, paged_statement)).all()))
    return Page(items=rows, total=total, page=pagination.page, page_size=pagination.page_size)
