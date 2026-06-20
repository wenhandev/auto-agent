#!/usr/bin/env python3
"""Prune the SQLite database to demo-only data.

Keeps:
  - User / org bootstrap rows (login)
  - LLM config
  - "Acme Supply Hub Demo" workflow (re-seeded from seed_workflow.json)

Removes test workflows, runs, sessions, credentials, triggers, recordings, etc.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
DB_PATH = BACKEND / "auto_agent.db"
SEED = Path(__file__).resolve().parent / "seed_workflow.json"
WORKFLOW_NAME = "Acme Supply Hub Demo"
DEFAULT_ORG_NAME = "Default Organization"
ADMIN_EMAIL = "admin@localhost"


def _prune_test_users(conn: sqlite3.Connection) -> dict[str, int]:
    """Keep only default org + admin user."""
    cur = conn.cursor()
    counts: dict[str, int] = {}

    cur.execute(
        "SELECT id FROM organization WHERE name = ?",
        (DEFAULT_ORG_NAME,),
    )
    default_org = cur.fetchone()
    if default_org is None:
        return counts
    default_org_id = default_org[0]

    cur.execute("SELECT id FROM user WHERE lower(email) = ?", (ADMIN_EMAIL,))
    admin = cur.fetchone()
    if admin is None:
        return counts
    admin_id = admin[0]

    cur.execute(
        "DELETE FROM org_membership WHERE org_id != ? OR user_id != ?",
        (default_org_id, admin_id),
    )
    counts["org_membership"] = cur.rowcount

    cur.execute("DELETE FROM user WHERE id != ?", (admin_id,))
    counts["user"] = cur.rowcount

    cur.execute("DELETE FROM organization WHERE id != ?", (default_org_id,))
    counts["organization"] = cur.rowcount

    conn.commit()
    return counts


def _backup_db() -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = DB_PATH.with_suffix(f".db.bak.{ts}")
    shutil.copy2(DB_PATH, dest)
    return dest


def _prune(conn: sqlite3.Connection) -> dict[str, int]:
    cur = conn.cursor()
    counts: dict[str, int] = {}

    def delete_all(table: str) -> None:
        cur.execute(f"DELETE FROM {table}")  # noqa: S608
        counts[table] = cur.rowcount

    for table in (
        "webhook_delivery",
        "webhook_subscription",
        "processed_event",
        "chat_message",
        "chat_session",
        "run_artifact",
        "run_event",
        "run_approval",
        "run",
        "selector_cache",
        "workflow_credential",
        "trigger",
        "workflow_version",
        "workflow",
        "browser_session",
        "browser_profile",
        "recording",
        "credential",
        "api_key",
        "route_skill",
        "proxy_config",
    ):
        delete_all(table)

    conn.commit()
    return counts


def _clear_artifact_dirs() -> int:
    removed = 0
    for root in (
        BACKEND / "data" / "artifacts",
        BACKEND / ".vision_artifacts",
    ):
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
                removed += 1
            elif child.is_file():
                child.unlink()
                removed += 1
    return removed


def _seed_demo_workflow() -> str:
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))

    os.chdir(BACKEND)

    from sqlmodel import Session, select

    from app.db.models import Workflow
    from app.db.session import engine
    from app.services import workflows as workflow_svc

    port = os.environ.get("AUTO_AGENT_PORT", "8765")
    demo_url = f"http://127.0.0.1:{port}/demo"

    with open(SEED, encoding="utf-8") as f:
        seed = json.load(f)
    wf_json = json.loads(json.dumps(seed["workflow"]).replace("{{DEMO_URL}}", demo_url))

    with Session(engine) as session:
        row = session.exec(
            select(Workflow).where(Workflow.name == WORKFLOW_NAME)
        ).first()
        if row is None:
            row = workflow_svc.create_workflow(
                WORKFLOW_NAME,
                session,
                description=seed.get(
                    "description",
                    "Deterministic demo workflow for client presentations",
                ),
                initial_workflow_json=wf_json,
                authored_by="manual",
            )
        else:
            workflow_svc.save_new_version(
                row.id,
                wf_json,
                "manual",
                session,
            )
        session.commit()
        return row.id


def main() -> int:
    if not DB_PATH.is_file():
        print(f"Database not found: {DB_PATH}", file=sys.stderr)
        return 1

    backup = _backup_db()
    print(f"Backup: {backup}")

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        counts = _prune(conn)
        conn.execute("PRAGMA foreign_keys = ON")
        user_counts = _prune_test_users(conn)
        counts.update(user_counts)
        conn.execute("VACUUM")
    finally:
        conn.close()

    artifacts_removed = _clear_artifact_dirs()
    wf_id = _seed_demo_workflow()

    print("Deleted rows:")
    for table, n in sorted(counts.items()):
        if n:
            print(f"  {table}: {n}")
    print(f"Artifact entries removed: {artifacts_removed}")
    print(f"Demo workflow ID: {wf_id}")
    print(f"Database size: {DB_PATH.stat().st_size / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
