"""Local workflow draft storage for desktop authoring."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


DRAFTS_DIR = Path.home() / ".auto-agent-worker" / "drafts"
DRAFTS_INDEX = DRAFTS_DIR / "index.json"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_index() -> list[dict[str, Any]]:
    if not DRAFTS_INDEX.is_file():
        return []
    try:
        data = json.loads(DRAFTS_INDEX.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _save_index(rows: list[dict[str, Any]]) -> None:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    DRAFTS_INDEX.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def list_drafts() -> list[dict[str, Any]]:
    from app.worker import publish_queue as publish_queue_svc

    queued_ids = {row.get("local_id") for row in publish_queue_svc.list_queue()}
    rows = sorted(_load_index(), key=lambda r: r.get("updated_at") or "", reverse=True)
    for row in rows:
        lid = row.get("local_id")
        row["publish_queued"] = bool(lid and lid in queued_ids)
    return rows


def get_draft(local_id: str) -> Optional[dict[str, Any]]:
    path = DRAFTS_DIR / f"{local_id}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def save_draft(
    *,
    draft_json: dict[str, Any],
    local_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    name: Optional[str] = None,
    cloud_version_id: Optional[str] = None,
) -> dict[str, Any]:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    lid = local_id or f"draft_{uuid.uuid4().hex[:12]}"
    now = _utcnow()
    existing = get_draft(lid)
    row = {
        "local_id": lid,
        "workflow_id": workflow_id,
        "name": name or (existing or {}).get("name") or "Untitled draft",
        "cloud_version_id": cloud_version_id or (existing or {}).get("cloud_version_id"),
        "published_at": (existing or {}).get("published_at"),
        "updated_at": now,
        "created_at": (existing or {}).get("created_at") or now,
    }
    payload = {**row, "draft_json": draft_json}
    (DRAFTS_DIR / f"{lid}.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    rows = [r for r in _load_index() if r.get("local_id") != lid]
    rows.append({k: row[k] for k in row})
    _save_index(rows)
    return payload


def pull_from_cloud(*, workflow_id: str, workflow_json: dict[str, Any], name: str) -> dict[str, Any]:
    return save_draft(
        draft_json=workflow_json,
        workflow_id=workflow_id,
        name=name,
    )


__all__ = ["get_draft", "list_drafts", "pull_from_cloud", "save_draft"]
