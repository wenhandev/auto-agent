"""Persist worker session credentials locally."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


CREDENTIALS_DIR = Path.home() / ".auto-agent-worker"
CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials.json"


def load_credentials() -> Optional[dict[str, Any]]:
    if not CREDENTIALS_FILE.is_file():
        return None
    try:
        data = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def save_credentials(
    *,
    cloud_url: str,
    worker_session_token: str,
    worker_id: str,
    org_id: str,
    web_session_token: str | None = None,
) -> None:
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "cloud_url": cloud_url.rstrip("/"),
        "worker_session_token": worker_session_token,
        "worker_id": worker_id,
        "org_id": org_id,
    }
    if web_session_token:
        payload["web_session_token"] = web_session_token
    CREDENTIALS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def clear_credentials() -> None:
    if CREDENTIALS_FILE.is_file():
        CREDENTIALS_FILE.unlink()


__all__ = ["load_credentials", "save_credentials", "clear_credentials", "CREDENTIALS_FILE"]
