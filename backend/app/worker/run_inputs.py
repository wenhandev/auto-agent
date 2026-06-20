"""Fetch run input files from cloud into the local workflow sandbox."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import httpx

from app.tools.sandbox import resolve_sandbox_path


logger = logging.getLogger(__name__)


async def materialize_input_files(
    *,
    cloud_url: str,
    token: str,
    run_id: str,
    workflow_id: str,
    input_files: list[dict[str, Any]],
) -> None:
    if not input_files:
        return
    base = cloud_url.rstrip("/")
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=120.0) as client:
        for spec in input_files:
            file_id = str(spec.get("file_id") or "")
            rel_path = str(spec.get("path") or "")
            if not file_id or not rel_path:
                continue
            url = f"{base}/api/v1/workers/runs/{run_id}/input-files/{file_id}"
            try:
                resp = await client.get(url, headers=headers)
            except Exception:
                logger.exception(
                    "input file fetch failed run=%s file=%s", run_id, file_id
                )
                raise
            if resp.status_code != 200:
                raise RuntimeError(
                    f"failed to fetch input file {file_id}: HTTP {resp.status_code}"
                )
            dest = resolve_sandbox_path(rel_path, workflow_id=workflow_id)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
            logger.info(
                "materialized input file run=%s path=%s bytes=%s",
                run_id,
                rel_path,
                len(resp.content),
            )


__all__ = ["materialize_input_files"]
