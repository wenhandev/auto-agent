"""Offline publish queue for desktop workflow drafts."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional


logger = logging.getLogger(__name__)

PUBLISH_QUEUE_FILE = Path.home() / ".auto-agent-worker" / "publish_queue.json"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_rows() -> list[dict[str, Any]]:
    if not PUBLISH_QUEUE_FILE.is_file():
        return []
    try:
        data = json.loads(PUBLISH_QUEUE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _save_rows(rows: list[dict[str, Any]]) -> None:
    PUBLISH_QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PUBLISH_QUEUE_FILE.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def list_queue() -> list[dict[str, Any]]:
    return sorted(_load_rows(), key=lambda r: r.get("queued_at") or "")


def is_queued(local_id: str) -> bool:
    return any(row.get("local_id") == local_id for row in _load_rows())


def enqueue(*, local_id: str, workflow_id: str, name: str | None = None) -> dict[str, Any]:
    rows = [r for r in _load_rows() if r.get("local_id") != local_id]
    row = {
        "local_id": local_id,
        "workflow_id": workflow_id,
        "name": name,
        "queued_at": _utcnow(),
        "attempts": 0,
        "last_error": None,
    }
    rows.append(row)
    _save_rows(rows)
    return row


def dequeue(local_id: str) -> None:
    rows = [r for r in _load_rows() if r.get("local_id") != local_id]
    _save_rows(rows)


def record_failure(local_id: str, error: str) -> None:
    rows = _load_rows()
    for row in rows:
        if row.get("local_id") == local_id:
            row["attempts"] = int(row.get("attempts") or 0) + 1
            row["last_error"] = error
            row["last_attempt_at"] = _utcnow()
    _save_rows(rows)


def flush_queue(
    *,
    publish_fn: Callable[[str], Any],
    approval_status: str,
) -> int:
    """Retry queued publishes. Returns number successfully published."""
    if approval_status != "approved":
        return 0
    published = 0
    for row in list_queue():
        local_id = str(row.get("local_id") or "")
        if not local_id:
            continue
        try:
            publish_fn(local_id)
            dequeue(local_id)
            published += 1
        except Exception as exc:
            logger.warning("publish queue retry failed for %s: %s", local_id, exc)
            record_failure(local_id, str(exc))
    return published


__all__ = [
    "PUBLISH_QUEUE_FILE",
    "dequeue",
    "enqueue",
    "flush_queue",
    "is_queued",
    "list_queue",
    "record_failure",
]
