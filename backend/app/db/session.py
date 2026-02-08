from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager

from sqlmodel import Session

from app.db.engine import get_engine


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
