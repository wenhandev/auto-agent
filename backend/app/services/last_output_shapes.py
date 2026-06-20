"""Load node output shapes from the most recent successful workflow run."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from sqlmodel import Session, select

from app.db.models import Run, RunEvent


@dataclass
class LastOutputShapes:
    run_id: Optional[str] = None
    started_at: Optional[datetime] = None
    shapes: dict[str, Any] = field(default_factory=dict)


def fetch_last_output_shapes(session: Session, workflow_id: str) -> LastOutputShapes:
    run = session.exec(
        select(Run)
        .where(Run.workflow_id == workflow_id, Run.status == "completed")
        .order_by(Run.started_at.desc())  # type: ignore[attr-defined]
    ).first()
    if run is None:
        return LastOutputShapes()

    events = session.exec(
        select(RunEvent)
        .where(RunEvent.run_id == run.id, RunEvent.event_type == "node_completed")
        .order_by(RunEvent.seq)  # type: ignore[attr-defined]
    ).all()

    shapes: dict[str, Any] = {}
    for ev in events:
        if not ev.node_id:
            continue
        try:
            payload = json.loads(ev.payload_json)
        except Exception:
            continue
        output = payload.get("output")
        if output is not None:
            shapes[ev.node_id] = output

    return LastOutputShapes(
        run_id=run.id,
        started_at=run.started_at,
        shapes=shapes,
    )


def preview_context_from_shapes(shapes: dict[str, Any]) -> dict[str, Any]:
    return {
        "nodes": {
            node_id: {"output": output}
            for node_id, output in shapes.items()
        }
    }


__all__ = ["LastOutputShapes", "fetch_last_output_shapes", "preview_context_from_shapes"]
