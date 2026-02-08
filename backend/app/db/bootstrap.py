from __future__ import annotations

from pathlib import Path

from sqlmodel import Session

from app.core.config import get_settings
from app.db.engine import create_engine_from_url, ensure_database_parent_dir
from app.db.migrations import upgrade_to_head
from app.db.seed import seed_initial_data


def initialize_database(
    database_url: str | None = None,
    *,
    seed: bool = True,
    project_root: Path | None = None,
) -> None:
    target_url = database_url or get_settings().database_url
    ensure_database_parent_dir(target_url)
    upgrade_to_head(target_url)

    if not seed:
        return

    engine = create_engine_from_url(target_url)
    try:
        with Session(engine) as session:
            seed_initial_data(session, project_root=project_root)
    finally:
        engine.dispose()
