from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.db import models  # noqa: F401  ensure models are registered with metadata
from app.settings import settings


def _engine_connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


DATABASE_URL = settings.database_url

engine = create_engine(
    DATABASE_URL,
    connect_args=_engine_connect_args(DATABASE_URL),
)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    from app.db.migrations import (
        ensure_browser_session_memory_column,
        ensure_browser_profile_antibot_columns,
        ensure_browser_session_provider_columns,
        ensure_run_browser_provider_columns,
        ensure_run_browser_session_column,
        ensure_run_proxy_id_column,
        ensure_run_worker_columns,
        ensure_desktop_client_columns,
        ensure_worker_tables,
    )

    ensure_run_proxy_id_column()
    ensure_run_browser_session_column()
    ensure_browser_profile_antibot_columns()
    ensure_browser_session_memory_column()
    ensure_browser_session_provider_columns()
    ensure_run_browser_provider_columns()
    ensure_worker_tables()
    ensure_desktop_client_columns()
    ensure_run_worker_columns()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


__all__ = ["engine", "init_db", "get_session"]
