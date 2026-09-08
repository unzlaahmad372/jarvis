"""Alembic environment configuration for JARVIS."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.core.config import get_settings
from app.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    url = config.get_main_option("sqlalchemy.url") or get_settings().database_url
    # Alembic uses the sync sqlite driver; strip +aiosqlite if present
    return url.replace("sqlite+aiosqlite", "sqlite")


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
