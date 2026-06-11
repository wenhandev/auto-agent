from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.db import models  # noqa: F401  ensure models are registered with metadata


DATABASE_URL = "sqlite:///./auto_agent.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


__all__ = ["engine", "init_db", "get_session"]
