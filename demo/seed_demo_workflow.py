#!/usr/bin/env python3
"""Seed the deterministic Acme Supply Hub demo workflow and enqueue a run."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

SEED = Path(__file__).resolve().parent / "seed_workflow.json"
WORKFLOW_NAME = "Acme Supply Hub Demo"


def _detect_port() -> str:
    port = os.environ.get("AUTO_AGENT_PORT")
    if port:
        return port
    for candidate in ("8000", "8765"):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{candidate}/demo", timeout=2):
                return candidate
        except Exception:
            continue
    raise SystemExit("No auto_agent backend found on ports 8000 or 8765")


def _seed_workflow_db(wf_json: dict, *, description: str) -> str:
    os.chdir(BACKEND)

    from sqlmodel import Session, select

    from app.db.models import Workflow
    from app.db.session import engine
    from app.services import workflows as workflow_svc

    with Session(engine) as session:
        row = session.exec(
            select(Workflow).where(Workflow.name == WORKFLOW_NAME)
        ).first()
        if row is None:
            row = workflow_svc.create_workflow(
                WORKFLOW_NAME,
                session,
                description=description,
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
            row.description = description
            session.add(row)
        session.commit()
        return row.id


def _start_run(wf_id: str, port: str) -> str:
    base = f"http://127.0.0.1:{port}"
    req = urllib.request.Request(
        f"{base}/api/workflows/{wf_id}/runs",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    return data["id"]


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Seed Acme Supply Hub demo workflow")
    parser.add_argument(
        "--no-run",
        action="store_true",
        help="Update workflow in DB only; do not enqueue a run",
    )
    args = parser.parse_args()

    port = _detect_port()
    demo_url = f"http://127.0.0.1:{port}/demo"

    with open(SEED) as f:
        seed = json.load(f)
    wf_json = json.loads(json.dumps(seed["workflow"]).replace("{{DEMO_URL}}", demo_url))

    wf_id = _seed_workflow_db(
        wf_json,
        description=seed.get(
            "description",
            "Deterministic demo workflow for client presentations",
        ),
    )
    print(f"Backend: http://127.0.0.1:{port}")
    print(f"Workflow ID: {wf_id}")
    if args.no_run:
        print("Workflow seeded (no run started).")
        return 0
    run_id = _start_run(wf_id, port)
    print(f"Run ID: {run_id}")
    print(f"Poll: curl -s http://127.0.0.1:{port}/api/runs/{run_id} | jq .run.status")
    return 0


if __name__ == "__main__":
    sys.exit(main())
