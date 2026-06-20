"""Relay run artifacts from worker disk to the cloud control plane."""

from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from app.services import artifacts as artifact_svc


logger = logging.getLogger(__name__)

SendFn = Callable[[dict[str, Any]], Awaitable[None]]

_pending: dict[str, asyncio.Future[str]] = {}


def handle_ack(frame: dict[str, Any]) -> None:
    upload_id = str(frame.get("upload_id") or "")
    artifact_id = frame.get("artifact_id")
    if not upload_id or not isinstance(artifact_id, str):
        return
    fut = _pending.get(upload_id)
    if fut is not None and not fut.done():
        fut.set_result(artifact_id)


async def upload_bytes(
    send: SendFn,
    *,
    run_id: str,
    kind: str,
    data: bytes,
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
    node_id: Optional[str] = None,
    step_index: Optional[int] = None,
    note: Optional[str] = None,
    timeout: float = 60.0,
) -> str:
    upload_id = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[str] = loop.create_future()
    _pending[upload_id] = fut
    try:
        await send(
            {
                "type": "artifact_upload",
                "run_id": run_id,
                "upload_id": upload_id,
                "kind": kind,
                "data_base64": base64.b64encode(data).decode("ascii"),
                "filename": filename,
                "content_type": content_type,
                "node_id": node_id,
                "step_index": step_index,
                "note": note,
            }
        )
        return await asyncio.wait_for(fut, timeout=timeout)
    finally:
        _pending.pop(upload_id, None)


async def upload_artifact_row(
    send: SendFn,
    *,
    run_id: str,
    row_id: str,
    node_id: Optional[str] = None,
    step_index: Optional[int] = None,
) -> Optional[str]:
    row = artifact_svc.get_artifact(row_id, run_id=run_id)
    if row is None:
        return None
    path = artifact_svc.resolve_path(row)
    if not path.is_file() or row.bytes == 0:
        return None
    data = path.read_bytes()
    return await upload_bytes(
        send,
        run_id=run_id,
        kind=row.kind,
        data=data,
        filename=row.filename or path.name,
        content_type=row.content_type,
        node_id=node_id or row.node_id,
        step_index=step_index if step_index is not None else row.step_index,
        note=row.note,
    )


async def relay_event_artifacts(
    send: SendFn,
    run_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Upload local artifacts referenced in a run event; return cloud artifact ids."""
    out = dict(payload)
    node_id = payload.get("node_id")
    step_index = payload.get("step_index")

    screenshot_ref = payload.get("screenshot_ref")
    if screenshot_ref:
        path = Path(str(screenshot_ref))
        if path.is_file():
            try:
                cloud_id = await upload_bytes(
                    send,
                    run_id=run_id,
                    kind="screenshot",
                    data=path.read_bytes(),
                    filename=path.name,
                    content_type="image/png",
                    node_id=node_id,
                    step_index=step_index,
                )
                out["artifact_id"] = cloud_id
            except Exception:
                logger.exception("screenshot relay failed run=%s", run_id)
        out.pop("screenshot_ref", None)

    artifact_id = out.get("artifact_id")
    if isinstance(artifact_id, str) and artifact_id:
        try:
            cloud_id = await upload_artifact_row(
                send,
                run_id=run_id,
                row_id=artifact_id,
                node_id=node_id,
                step_index=step_index,
            )
            if cloud_id:
                out["artifact_id"] = cloud_id
        except Exception:
            logger.exception("artifact relay failed run=%s artifact=%s", run_id, artifact_id)

    output = out.get("output")
    if isinstance(output, dict):
        out_output = dict(output)
        out_artifact = out_output.get("artifact_id")
        if isinstance(out_artifact, str) and out_artifact:
            try:
                cloud_id = await upload_artifact_row(
                    send,
                    run_id=run_id,
                    row_id=out_artifact,
                    node_id=node_id,
                    step_index=step_index,
                )
                if cloud_id:
                    out_output["artifact_id"] = cloud_id
                    out["output"] = out_output
            except Exception:
                logger.exception(
                    "output artifact relay failed run=%s artifact=%s",
                    run_id,
                    out_artifact,
                )
    return out


def reset_for_tests() -> None:
    for fut in _pending.values():
        if not fut.done():
            fut.cancel()
    _pending.clear()


__all__ = [
    "handle_ack",
    "relay_event_artifacts",
    "reset_for_tests",
    "upload_artifact_row",
    "upload_bytes",
]
