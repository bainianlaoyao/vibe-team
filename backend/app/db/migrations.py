from __future__ import annotations

from pathlib import Path

from alembic.config import Config

from alembic import command
from app.core.config import get_settings
from app.db.engine import ensure_database_parent_dir

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI_PATH = PROJECT_ROOT / "alembic.ini"
ALEMBIC_SCRIPT_LOCATION = PROJECT_ROOT / "alembic"


def build_alembic_config(database_url: str | None = None) -> Config:
    target_database_url = database_url or get_settings().database_url
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(ALEMBIC_SCRIPT_LOCATION))
    config.set_main_option("sqlalchemy.url", target_database_url)
    return config


def upgrade_to_head(database_url: str | None = None) -> None:
    target_database_url = database_url or get_settings().database_url
    ensure_database_parent_dir(target_database_url)
    command.upgrade(build_alembic_config(target_database_url), "head")
