"""Store download/print outputs via the artifact store or a temp fallback."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from app.services import artifact_context
from app.services import artifacts as artifact_svc


def store_download_bytes(
    data: bytes,
    *,
    filename: str,
    node_id: str | None = None,
) -> dict[str, Any]:
    run_id = artifact_context.get_run_id()
    if run_id:
        row = artifact_svc.store_bytes(
            run_id,
            "download",
            data,
            filename=filename,
            node_id=node_id,
        )
        return {
            "artifact_id": row.id,
            "filename": filename,
            "bytes": len(data),
        }

    suffix = Path(filename).suffix or ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(data)
        temp_path = tmp.name
    return {
        "artifact_id": temp_path,
        "filename": filename,
        "bytes": len(data),
        "degraded": "no artifact store; saved to temp file",
    }


__all__ = ["store_download_bytes"]
