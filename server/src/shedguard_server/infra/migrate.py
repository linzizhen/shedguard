"""启动时执行 Alembic 迁移，保证表结构与代码版本一致。"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def run_migrations(db_url: str) -> None:
    """升级到最新版本；sqlalchemy.url 需要转义 % 以免被 configparser 插值。"""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))
    command.upgrade(config, "head")