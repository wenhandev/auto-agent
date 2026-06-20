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


def add_parent_run_id_on_first_run() -> None:
    """Add ``parent_run_id`` to the ``run`` table when missing."""
    marker = _BACKEND_ROOT / ".parent_run_id_added"
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "run")
        except Exception:
            return
        if not cols:
            return
        if "parent_run_id" not in cols:
            conn.exec_driver_sql("ALTER TABLE run ADD COLUMN parent_run_id TEXT")
            logger.warning("run table migration: added column 'parent_run_id'")
    marker.write_text("ok\n", encoding="utf-8")


def add_credential_type_column() -> None:
    """Add ``type`` column to ``credential`` (default ``generic``)."""
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "credential")
        except Exception:
            return
        if not cols:
            return
        if "type" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE credential ADD COLUMN type TEXT NOT NULL DEFAULT 'generic'"
            )
            logger.warning("credential table migration: added column 'type'")


def ensure_trigger_poll_app_columns() -> None:
    """Add poll/app trigger columns to ``trigger`` when missing."""
    additions: list[tuple[str, str]] = [
        ("poll_app", "TEXT"),
        ("poll_resource", "TEXT"),
        ("poll_operation", "TEXT"),
        ("poll_credential", "TEXT"),
        ("poll_dedup_path", "TEXT"),
        ("poll_cursor", "TEXT"),
        ("last_seen_key", "TEXT"),
        ("seen_keys_json", "TEXT"),
        ("poll_mode", "TEXT NOT NULL DEFAULT 'per_record'"),
        ("on_first_poll", "TEXT NOT NULL DEFAULT 'fire_none'"),
        ("min_poll_interval_s", "INTEGER NOT NULL DEFAULT 60"),
        ("last_polled_at", "TEXT"),
        ("first_poll_done", "INTEGER NOT NULL DEFAULT 0"),
        ("app_name", "TEXT"),
        ("app_trigger", "TEXT"),
        ("app_credential", "TEXT"),
        ("subscription_id", "TEXT"),
        ("subscription_secret_ciphertext", "BLOB"),
    ]
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "trigger")
        except Exception:
            return
        if not cols:
            return
        for name, ddl in additions:
            if name not in cols:
                conn.exec_driver_sql(f"ALTER TABLE trigger ADD COLUMN {name} {ddl}")
                logger.warning("trigger table migration: added column %r", name)


def ensure_run_mode_and_task_columns() -> None:
    """Add ``mode`` and autonomous task columns to ``run`` when missing."""
    additions: list[tuple[str, str]] = [
        ("mode", "TEXT NOT NULL DEFAULT 'graph'"),
        ("objective", "TEXT"),
        ("start_url", "TEXT"),
        ("max_steps", "INTEGER"),
        ("max_seconds", "INTEGER"),
        ("success_criteria", "TEXT"),
        ("allowed_domains_json", "TEXT"),
        ("data_schema_json", "TEXT"),
        ("require_confirmation", "INTEGER NOT NULL DEFAULT 0"),
        ("allowed_tools_json", "TEXT"),
        ("result_json", "TEXT"),
    ]
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "run")
        except Exception:
            return
        if not cols:
            return
        for name, ddl in additions:
            if name not in cols:
                conn.exec_driver_sql(f"ALTER TABLE run ADD COLUMN {name} {ddl}")
                logger.warning("run table migration: added column %r", name)


def ensure_run_browser_profile_column() -> None:
    """Add ``browser_profile_id`` to ``run`` when missing."""
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "run")
        except Exception:
            return
        if not cols:
            return
        if "browser_profile_id" not in cols:
            conn.exec_driver_sql("ALTER TABLE run ADD COLUMN browser_profile_id TEXT")
            logger.warning("run table migration: added column 'browser_profile_id'")


def ensure_run_browser_session_column() -> None:
    """Add ``browser_session_id`` to ``run`` when missing."""
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "run")
        except Exception:
            return
        if not cols:
            return
        if "browser_session_id" not in cols:
            conn.exec_driver_sql("ALTER TABLE run ADD COLUMN browser_session_id TEXT")
            logger.warning("run table migration: added column 'browser_session_id'")


def ensure_browser_session_memory_column() -> None:
    """Add compact agent memory storage to ``browser_session`` when missing."""
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "browser_session")
        except Exception:
            return
        if not cols:
            return
        if "memory_json" not in cols:
            conn.exec_driver_sql("ALTER TABLE browser_session ADD COLUMN memory_json TEXT")
            logger.warning(
                "browser_session table migration: added column 'memory_json'"
            )


def ensure_browser_session_provider_columns() -> None:
    """Add browser provider fields to ``browser_session`` when missing."""
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "browser_session")
        except Exception:
            return
        if not cols:
            return
        if "provider_id" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE browser_session ADD COLUMN provider_id TEXT "
                "NOT NULL DEFAULT 'local_playwright'"
            )
            logger.warning(
                "browser_session table migration: added column 'provider_id'"
            )
        if "provider_metadata_json" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE browser_session ADD COLUMN provider_metadata_json TEXT"
            )
            logger.warning(
                "browser_session table migration: added column 'provider_metadata_json'"
            )


def ensure_run_browser_provider_columns() -> None:
    """Add browser provider audit fields and loop metrics to ``run`` when missing."""
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "run")
        except Exception:
            return
        if not cols:
            return
        if "browser_provider_id" not in cols:
            conn.exec_driver_sql("ALTER TABLE run ADD COLUMN browser_provider_id TEXT")
            logger.warning("run table migration: added column 'browser_provider_id'")
        if "browser_provider_metadata_json" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE run ADD COLUMN browser_provider_metadata_json TEXT"
            )
            logger.warning(
                "run table migration: added column 'browser_provider_metadata_json'"
            )
        if "agent_loop_metrics_json" not in cols:
            conn.exec_driver_sql("ALTER TABLE run ADD COLUMN agent_loop_metrics_json TEXT")
            logger.warning("run table migration: added column 'agent_loop_metrics_json'")


def ensure_workflow_status_column() -> None:
    """Add ``status`` column to ``workflow`` (default ``active``)."""
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "workflow")
        except Exception:
            return
        if not cols:
            return
        if "status" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE workflow ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
            )
            logger.warning("workflow table migration: added column 'status'")


def ensure_workflow_version_parameters_column() -> None:
    """Add ``parameters_json`` to ``workflow_version`` (default ``[]``)."""
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "workflow_version")
        except Exception:
            return
        if not cols:
            return
        if "parameters_json" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE workflow_version ADD COLUMN parameters_json "
                "TEXT NOT NULL DEFAULT '[]'"
            )
            logger.warning(
                "workflow_version table migration: added column 'parameters_json'"
            )


def ensure_run_parameters_json_column() -> None:
    """Add ``parameters_json`` to ``run`` when missing."""
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "run")
        except Exception:
            return
        if not cols:
            return
        if "parameters_json" not in cols:
            conn.exec_driver_sql("ALTER TABLE run ADD COLUMN parameters_json TEXT")
            logger.warning("run table migration: added column 'parameters_json'")


def ensure_trigger_scheduling_columns() -> None:
    """Add cron scheduling columns to ``trigger`` when missing."""
    columns = {
        "timezone": "TEXT NOT NULL DEFAULT 'Asia/Shanghai'",
        "next_run_at": "TEXT",
        "misfire_policy": "TEXT NOT NULL DEFAULT 'skip'",
    }
    with engine.connect() as conn:
        cols = _column_names(conn, "trigger")
        for name, ddl in columns.items():
            if name in cols:
                continue
            conn.exec_driver_sql(f"ALTER TABLE trigger ADD COLUMN {name} {ddl}")
            logger.warning("trigger table migration: added column %r", name)
        conn.commit()


def ensure_trigger_parameters_json_column() -> None:
    """Add ``parameters_json`` to ``trigger`` when missing."""
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "trigger")
        except Exception:
            return
        if not cols:
            return
        if "parameters_json" not in cols:
            conn.exec_driver_sql("ALTER TABLE trigger ADD COLUMN parameters_json TEXT")
            logger.warning("trigger table migration: added column 'parameters_json'")


def ensure_run_totp_identifier_column() -> None:
    """Add ``totp_identifier`` to ``run`` when missing."""
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "run")
        except Exception:
            return
        if not cols:
            return
        if "totp_identifier" not in cols:
            conn.exec_driver_sql("ALTER TABLE run ADD COLUMN totp_identifier TEXT")
            logger.warning("run table migration: added column 'totp_identifier'")


def ensure_run_record_video_column() -> None:
    """Add optional per-run session recording override when missing."""
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "run")
        except Exception:
            return
        if not cols:
            return
        if "record_video" not in cols:
            conn.exec_driver_sql("ALTER TABLE run ADD COLUMN record_video INTEGER")
            logger.warning("run table migration: added column 'record_video'")


def ensure_run_cost_columns() -> None:
    """Add per-run cost aggregation columns when missing."""
    additions = {
        "total_input_tokens": "INTEGER NOT NULL DEFAULT 0",
        "total_output_tokens": "INTEGER NOT NULL DEFAULT 0",
        "total_llm_calls": "INTEGER NOT NULL DEFAULT 0",
        "total_vision_calls": "INTEGER NOT NULL DEFAULT 0",
        "estimated_cost_usd": "REAL",
        "cost_note": "TEXT",
        "usage_summary_json": "TEXT",
        "node_cost_json": "TEXT",
    }
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "run")
        except Exception:
            return
        if not cols:
            return
        for name, ddl in additions.items():
            if name not in cols:
                conn.exec_driver_sql(f"ALTER TABLE run ADD COLUMN {name} {ddl}")
                logger.warning("run table migration: added column %r", name)


def ensure_selector_cache_column() -> None:
    """Add ``selector_cache_enabled`` to ``llm_config`` when missing."""
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "llm_config")
        except Exception:
            return
        if not cols:
            return
        if "selector_cache_enabled" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE llm_config ADD COLUMN selector_cache_enabled "
                "INTEGER NOT NULL DEFAULT 1"
            )
            logger.warning(
                "llm_config table migration: added column 'selector_cache_enabled'"
            )


def ensure_run_proxy_id_column() -> None:
    """Add ``proxy_id`` to ``run`` when missing."""
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "run")
        except Exception:
            return
        if not cols:
            return
        if "proxy_id" not in cols:
            conn.exec_driver_sql("ALTER TABLE run ADD COLUMN proxy_id TEXT")
            logger.warning("run table migration: added column 'proxy_id'")


def ensure_browser_profile_antibot_columns() -> None:
    """Add locale/timezone/proxy columns to ``browser_profile`` when missing."""
    additions = {
        "locale": "TEXT",
        "timezone_id": "TEXT",
        "proxy_id": "TEXT",
    }
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "browser_profile")
        except Exception:
            return
        if not cols:
            return
        for name, ddl in additions.items():
            if name not in cols:
                conn.exec_driver_sql(
                    f"ALTER TABLE browser_profile ADD COLUMN {name} {ddl}"
                )
                logger.warning(
                    "browser_profile table migration: added column %r", name
                )


_ORG_BACKFILL_MARKER = _BACKEND_ROOT / ".org_backfilled"


def ensure_workflow_visibility_column() -> None:
    """Add ``visibility`` column to workflow (private | org)."""
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "workflow")
        except Exception:
            return
        if not cols:
            return
        if "visibility" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE workflow ADD COLUMN visibility TEXT NOT NULL DEFAULT 'org'"
            )
            logger.warning("workflow table migration: added column 'visibility'")


def ensure_org_columns() -> None:
    """Add ``org_id`` / ``created_by`` columns for multi-tenant scoping."""
    table_additions: dict[str, list[tuple[str, str]]] = {
        "workflow": [
            ("org_id", "TEXT"),
            ("created_by", "TEXT"),
            ("visibility", "TEXT NOT NULL DEFAULT 'org'"),
        ],
        "run": [
            ("org_id", "TEXT"),
        ],
        "credential": [
            ("org_id", "TEXT"),
            ("created_by", "TEXT"),
        ],
        "api_key": [
            ("org_id", "TEXT"),
        ],
    }
    with engine.begin() as conn:
        for table, additions in table_additions.items():
            try:
                cols = _column_names(conn, table)
            except Exception:
                continue
            if not cols:
                continue
            for name, ddl in additions:
                if name not in cols:
                    conn.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"
                    )
                    logger.warning(
                        "%s table migration: added column %r", table, name
                    )


def bootstrap_orgs_on_startup() -> None:
    """Ensure default org/admin exist and backfill legacy rows once."""
    from app.services.orgs import backfill_org_ownership, ensure_bootstrap

    with Session(engine) as session:
        ensure_bootstrap(session)
    backfill_org_ownership(_ORG_BACKFILL_MARKER)


def ensure_run_worker_columns() -> None:
    """Add worker dispatch columns to ``run`` when missing."""
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "run")
        except Exception:
            return
        if not cols:
            return
        additions = [
            ("execution_mode", "TEXT NOT NULL DEFAULT 'cloud'"),
            ("worker_id", "TEXT"),
            ("worker_pool", "TEXT"),
            ("worker_assigned_at", "TEXT"),
        ]
        for name, ddl in additions:
            if name not in cols:
                conn.exec_driver_sql(f"ALTER TABLE run ADD COLUMN {name} {ddl}")
                logger.warning("run table migration: added column %r", name)


def ensure_user_identity_table() -> None:
    from sqlmodel import SQLModel

    from app.db.models import UserIdentity

    SQLModel.metadata.create_all(
        engine,
        tables=[UserIdentity.__table__],  # type: ignore[attr-defined]
        checkfirst=True,
    )


def ensure_worker_tables() -> None:
    """Ensure worker and worker_session tables exist (create_all handles fresh DB)."""
    from sqlmodel import SQLModel

    from app.db.models import Worker, WorkerSession

    SQLModel.metadata.create_all(
        engine,
        tables=[Worker.__table__, WorkerSession.__table__],  # type: ignore[attr-defined]
        checkfirst=True,
    )


def ensure_desktop_client_columns() -> None:
    """Add desktop client policy and worker approval columns when missing."""
    with engine.begin() as conn:
        try:
            org_cols = _column_names(conn, "organization")
        except Exception:
            org_cols = set()
        if org_cols and "desktop_client_policy" not in org_cols:
            conn.exec_driver_sql(
                "ALTER TABLE organization ADD COLUMN desktop_client_policy "
                "TEXT NOT NULL DEFAULT 'approval_required'"
            )
            logger.warning(
                "organization table migration: added column 'desktop_client_policy'"
            )

        try:
            worker_cols = _column_names(conn, "worker")
        except Exception:
            worker_cols = set()
        if not worker_cols:
            return
        worker_additions = [
            ("approval_status", "TEXT NOT NULL DEFAULT 'approved'"),
            ("approved_at", "TEXT"),
            ("approved_by_user_id", "TEXT"),
        ]
        for name, ddl in worker_additions:
            if name not in worker_cols:
                conn.exec_driver_sql(f"ALTER TABLE worker ADD COLUMN {name} {ddl}")
                logger.warning("worker table migration: added column %r", name)


def ensure_user_platform_admin_column() -> None:
    with engine.begin() as conn:
        try:
            cols = _column_names(conn, "user")
        except Exception:
            return
        if cols and "is_platform_admin" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE user ADD COLUMN is_platform_admin INTEGER NOT NULL DEFAULT 0"
            )
            logger.warning("user table migration: added column 'is_platform_admin'")


def ensure_oauth_domain_rule_table() -> None:
    from sqlmodel import SQLModel

    from app.db.models import OAuthDomainRule

    SQLModel.metadata.create_all(
        engine,
        tables=[OAuthDomainRule.__table__],  # type: ignore[attr-defined]
        checkfirst=True,
    )


__all__ = [
    "cleanup_credentials_on_first_run",
    "ensure_run_trigger_columns",
    "add_self_heal_columns_if_missing",
    "self_healing_default_on_first_run",
    "add_parent_run_id_on_first_run",
    "add_credential_type_column",
    "ensure_trigger_poll_app_columns",
    "ensure_run_mode_and_task_columns",
    "ensure_run_browser_profile_column",
    "ensure_workflow_status_column",
    "ensure_workflow_version_parameters_column",
    "ensure_run_parameters_json_column",
    "ensure_run_totp_identifier_column",
    "ensure_run_record_video_column",
    "ensure_run_cost_columns",
    "ensure_selector_cache_column",
    "ensure_trigger_parameters_json_column",
    "ensure_trigger_scheduling_columns",
    "ensure_run_proxy_id_column",
    "ensure_browser_profile_antibot_columns",
    "ensure_org_columns",
    "ensure_workflow_visibility_column",
    "bootstrap_orgs_on_startup",
    "ensure_worker_tables",
    "ensure_run_worker_columns",
    "ensure_desktop_client_columns",
    "ensure_user_platform_admin_column",
    "ensure_oauth_domain_rule_table",
]

