"""One-off migration helpers run at backend startup.

Each helper is idempotent: it either inspects DB state or uses a small
marker file under ``backend/`` to make sure it never runs twice in
its destructive form. Logs a single line per applied migration so the
operator can see what happened.
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import delete, text
from sqlmodel import Session, select

from app.db.models import Credential, LlmConfig, WorkflowCredential
from app.db.session import engine


logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_CLEARED_MARKER = _BACKEND_ROOT / ".cleared_credentials"
_SELF_HEAL_MARKER = _BACKEND_ROOT / ".self_healing_default_set"


def cleanup_credentials_on_first_run() -> None:
    """Wipe every row in ``credential`` exactly once (the operator asked
    for a clean reset after introducing per-workflow scoping). The marker
    file makes the helper a no-op on subsequent boots so freshly created
    credentials are NOT touched.
    """
    if _CLEARED_MARKER.exists():
        return

    with Session(engine) as session:
        rows = session.exec(select(Credential)).all()
        if not rows:
            _CLEARED_MARKER.write_text("no rows to clear\n", encoding="utf-8")
            logger.warning(
                "credential cleanup migration: no rows present; marker written"
            )
            return

        session.exec(delete(WorkflowCredential))
        session.exec(delete(Credential))
        session.commit()

    _CLEARED_MARKER.write_text("ok\n", encoding="utf-8")
    logger.warning(
        "credential cleanup migration: removed %d existing credential row(s); "
        "operator requested a clean reset after introducing per-workflow scoping",
        len(rows),
    )


def _column_names(conn, table: str) -> set[str]:
    rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    return {str(r[1]) for r in rows}


def ensure_run_trigger_columns() -> None:
    """Add `source`, `trigger_id`, `trigger_context_json` to the `run`
    table when missing. Safe to run on every boot."""
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "run")
        except Exception:
            return
        if not cols:
            return
        if "source" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE run ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'"
            )
            logger.warning("run table migration: added column 'source'")
        if "trigger_id" not in cols:
            conn.exec_driver_sql("ALTER TABLE run ADD COLUMN trigger_id TEXT")
            logger.warning("run table migration: added column 'trigger_id'")
        if "trigger_context_json" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE run ADD COLUMN trigger_context_json TEXT"
            )
            logger.warning(
                "run table migration: added column 'trigger_context_json'"
            )


def add_self_heal_columns_if_missing() -> None:
    """Add `self_healing_enabled` AND `self_healing_vision_threshold` columns
    to the `llm_config` table when missing. Safe to run on every boot."""
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "llm_config")
        except Exception:
            return
        if not cols:
            return
        if "self_healing_enabled" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE llm_config ADD COLUMN self_healing_enabled "
                "INTEGER NOT NULL DEFAULT 1"
            )
            logger.warning(
                "llm_config table migration: added column 'self_healing_enabled'"
            )
        if "self_healing_vision_threshold" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE llm_config ADD COLUMN self_healing_vision_threshold "
                "REAL NOT NULL DEFAULT 0.6"
            )
            logger.warning(
                "llm_config table migration: added column "
                "'self_healing_vision_threshold'"
            )


def self_healing_default_on_first_run() -> None:
    """Idempotent backfill: ensure existing `llm_config` rows have
    `self_healing_enabled = True` AND `self_healing_vision_threshold = 0.6`.
    Writes a marker so subsequent boots are a no-op."""
    if _SELF_HEAL_MARKER.exists():
        return

    with Session(engine) as session:
        rows = session.exec(select(LlmConfig)).all()
        touched = 0
        for row in rows:
            changed = False
            if row.self_healing_enabled is None:  # type: ignore[unreachable]
                row.self_healing_enabled = True
                changed = True
            if (
                row.self_healing_vision_threshold is None  # type: ignore[unreachable]
                or row.self_healing_vision_threshold < 0.0
                or row.self_healing_vision_threshold > 1.0
            ):
                row.self_healing_vision_threshold = 0.6
                changed = True
            if changed:
                session.add(row)
                touched += 1
        if touched:
            session.commit()

    _SELF_HEAL_MARKER.write_text("ok\n", encoding="utf-8")
    logger.warning(
        "self-heal backfill migration: marker written (touched %d row(s))", touched
    )


__all__ = [
    "cleanup_credentials_on_first_run",
    "ensure_run_trigger_columns",
    "add_self_heal_columns_if_missing",
    "self_healing_default_on_first_run",
]
