from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine import Engine, make_url
from sqlmodel import create_engine

from app.core.config import get_settings

_engine: Engine | None = None


def _sqlite_connect_args(database_url: str) -> dict[str, bool]:
    is_sqlite = make_url(database_url).drivername.split("+", maxsplit=1)[0] == "sqlite"
    return {"check_same_thread": False} if is_sqlite else {}


def create_engine_from_url(database_url: str, *, echo: bool = False) -> Engine:
    return create_engine(
        database_url,
        echo=echo,
        connect_args=_sqlite_connect_args(database_url),
    )


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        # SQLALCHEMY_ECHO 优先；未设置时，仅在 debug 非 test 模式下启用
        if settings.sqlalchemy_echo is not None:
            echo = settings.sqlalchemy_echo
        else:
            echo = settings.debug and not settings.testing
        _engine = create_engine_from_url(
            settings.database_url,
            echo=echo,
        )
    return _engine


def dispose_engine() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def resolve_sqlite_database_path(database_url: str) -> Path | None:
    parsed_url = make_url(database_url)
    is_sqlite = parsed_url.drivername.split("+", maxsplit=1)[0] == "sqlite"
    if not is_sqlite:
        return None

    database = parsed_url.database
    if database is None or database in {"", ":memory:"}:
        return None

    db_path = Path(database)
    if not db_path.is_absolute():
        db_path = (Path.cwd() / db_path).resolve()
    return db_path


def ensure_database_parent_dir(database_url: str) -> None:
    db_path = resolve_sqlite_database_path(database_url)
    if db_path is None:
        return
    # 确保父目录存在（包括 .beebeebrain 目录）
    db_path.parent.mkdir(parents=True, exist_ok=True)
