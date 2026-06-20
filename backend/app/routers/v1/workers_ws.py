"""WebSocket endpoint for local runtime workers."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.auth.worker_auth import WorkerAuth, require_worker_session
from app.services import worker_hub


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workers", tags=["workers"])


@router.websocket("/connect")
async def worker_connect(
    websocket: WebSocket,
    auth: WorkerAuth = Depends(require_worker_session),
) -> None:
    await websocket.accept()
    worker = auth.worker
    initial: dict = {}
    try:
        raw = await websocket.receive_text()
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            initial = parsed
    except Exception:
        initial = {}

    max_runs = int(initial.get("max_concurrent_runs") or worker.max_concurrent_runs or 1)
    tags = initial.get("tags")
    tag_list = list(tags) if isinstance(tags, list) else None
    environment = initial.get("environment")
    env_dict = environment if isinstance(environment, dict) else None

    conn = await worker_hub.register_connection(
        worker.id,
        worker.org_id,
        websocket,
        max_concurrent_runs=max_runs,
        tags=tag_list,
        environment=env_dict,
    )

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                frame = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(frame, dict):
                continue
            frame_type = frame.get("type")
            if frame_type == "heartbeat":
                await worker_hub.handle_heartbeat(worker.id, frame)
            elif frame_type == "run_event":
                await worker_hub.handle_run_event(worker.id, frame)
            elif frame_type == "artifact_upload":
                ack = await worker_hub.handle_artifact_upload(worker.id, frame)
                if ack is not None:
                    await websocket.send_json(ack)
            elif frame_type == "stream_frame":
                await worker_hub.handle_stream_frame(worker.id, frame)
            elif frame_type == "environment":
                env = frame.get("environment")
                if isinstance(env, dict):
                    await worker_hub.handle_heartbeat(
                        worker.id, {"environment": env, "active_runs": conn.active_runs}
                    )
    except WebSocketDisconnect:
        logger.info("worker disconnected worker=%s", worker.id)
    except Exception:
        logger.exception("worker websocket error worker=%s", worker.id)
    finally:
        await worker_hub.unregister_connection(worker.id)


__all__ = ["router"]
