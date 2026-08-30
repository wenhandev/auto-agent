"""Desktop runtime sidecar: localhost HTTP API + worker WebSocket."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.worker.desktop_api import DesktopApi, DesktopApiError, sse_event_line
from app.worker.desktop_runtime import (
    DAEMON_HOST,
    DAEMON_PORT,
    DaemonState,
    DesktopRuntime,
    start_background_tasks,
    stop_background_tasks,
)


logger = logging.getLogger(__name__)

# Re-export for tests and legacy imports.
__all__ = [
    "DAEMON_HOST",
    "DAEMON_PORT",
    "DaemonState",
    "DesktopRuntime",
    "create_daemon_app",
    "run_daemon",
]


class SessionBody(BaseModel):
    cloud_url: str = Field(min_length=4)
    worker_session_token: str = Field(min_length=8)
    worker_id: str = Field(min_length=4)
    org_id: str = Field(min_length=4)
    web_session_token: str | None = None


class RunStartBody(BaseModel):
    workflow_id: str | None = None
    workflow: dict[str, Any] | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    trigger_namespace: dict[str, Any] = Field(default_factory=dict)


class DraftSaveBody(BaseModel):
    draft_json: dict[str, Any]
    local_id: str | None = None
    workflow_id: str | None = None
    name: str | None = None


def _http_error(exc: DesktopApiError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.message)


def create_daemon_app(state: Optional[DesktopRuntime] = None) -> FastAPI:
    runtime_state = state or DesktopRuntime()
    runtime_state.refresh_credentials()
    api = DesktopApi(runtime_state)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await start_background_tasks(runtime_state)
        yield
        await stop_background_tasks(runtime_state)

    app = FastAPI(title="Auto Agent Desktop Runtime", lifespan=lifespan)

    @app.get("/doctor")
    async def doctor() -> dict[str, Any]:
        return await api.run_doctor()

    @app.get("/health")
    def health() -> dict[str, str]:
        return api.health()

    @app.get("/ready")
    def ready() -> dict[str, Any]:
        return api.ready()

    @app.get("/status")
    def status() -> dict[str, Any]:
        return api.get_status()

    @app.post("/session")
    async def save_session(body: SessionBody) -> dict[str, str]:
        try:
            return await api.save_session(body.model_dump())
        except DesktopApiError as exc:
            raise _http_error(exc) from exc

    @app.delete("/session")
    async def clear_session() -> dict[str, str]:
        return await api.clear_session()

    @app.get("/settings/llm")
    def get_llm_settings() -> dict[str, Any]:
        return api.get_llm_settings()

    @app.put("/settings/llm")
    def put_llm_settings(body: dict[str, Any]) -> dict[str, Any]:
        return api.put_llm_settings(body)

    @app.get("/settings/computer-use")
    def get_computer_use_settings() -> dict[str, Any]:
        return api.get_computer_use_settings()

    @app.put("/settings/computer-use")
    def put_computer_use_settings(body: dict[str, Any]) -> dict[str, Any]:
        return api.put_computer_use_settings(body)

    @app.get("/cloud/workflows")
    def list_cloud_workflows() -> Any:
        try:
            return api.list_cloud_workflows()
        except DesktopApiError as exc:
            raise _http_error(exc) from exc

    @app.get("/cloud/workflows/{workflow_id}")
    def get_cloud_workflow(workflow_id: str) -> Any:
        try:
            return api.get_cloud_workflow(workflow_id)
        except DesktopApiError as exc:
            raise _http_error(exc) from exc

    @app.post("/cloud/workflows/{workflow_id}/pull")
    def pull_cloud_workflow(workflow_id: str) -> dict[str, Any]:
        try:
            return api.pull_cloud_workflow(workflow_id)
        except DesktopApiError as exc:
            raise _http_error(exc) from exc

    @app.get("/drafts")
    def list_drafts() -> list[dict[str, Any]]:
        return api.list_drafts()

    @app.get("/drafts/{local_id}")
    def get_draft(local_id: str) -> dict[str, Any]:
        try:
            return api.get_draft(local_id)
        except DesktopApiError as exc:
            raise _http_error(exc) from exc

    @app.post("/drafts")
    def save_draft(body: DraftSaveBody) -> dict[str, Any]:
        return api.save_draft(body.model_dump())

    @app.post("/drafts/{local_id}/publish")
    def publish_draft(local_id: str) -> JSONResponse:
        try:
            version = api.publish_draft(local_id)
            status = int(version.pop("_http_status", 200))
            return JSONResponse(version, status_code=status)
        except DesktopApiError as exc:
            raise _http_error(exc) from exc

    @app.get("/publish-queue")
    def get_publish_queue() -> list[dict[str, Any]]:
        return api.list_publish_queue()

    @app.post("/publish-queue/retry")
    async def retry_publish_queue() -> dict[str, Any]:
        return await api.retry_publish_queue()

    @app.get("/runs")
    def list_runs() -> list[dict[str, Any]]:
        return api.list_runs()

    @app.post("/runs")
    async def start_run(body: RunStartBody) -> JSONResponse:
        try:
            meta = await api.start_run(body.model_dump())
            status = int(meta.pop("_http_status", 201))
            return JSONResponse(meta, status_code=status)
        except DesktopApiError as exc:
            raise _http_error(exc) from exc

    @app.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        try:
            return api.get_run(run_id)
        except DesktopApiError as exc:
            raise _http_error(exc) from exc

    @app.post("/runs/{run_id}/abort")
    async def abort_run(run_id: str) -> dict[str, str]:
        try:
            return await api.abort_run(run_id)
        except DesktopApiError as exc:
            raise _http_error(exc) from exc

    @app.get("/runs/{run_id}/events")
    async def run_events(run_id: str) -> StreamingResponse:
        try:

            async def event_stream():
                async for payload in api.iter_run_events(run_id):
                    line = sse_event_line(payload)
                    if line:
                        yield line

            return StreamingResponse(
                event_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        except DesktopApiError as exc:
            raise _http_error(exc) from exc

    @app.websocket("/ws/stream/{run_id}")
    async def ws_stream(run_id: str, ws: WebSocket) -> None:
        await ws.accept()
        if runtime_state.runs.get_run(run_id) is None:
            await ws.close(code=4404)
            return
        viewers = runtime_state._stream_viewers.setdefault(run_id, set())
        viewers.add(ws)
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=64)
        runtime_state.runs._subscribers.setdefault(run_id, []).append(queue)
        try:
            while True:
                payload = await queue.get()
                if payload is None:
                    await ws.send_json({"type": "stream_ended"})
                    break
                if payload.get("type") == "stream_frame":
                    await ws.send_json({
                        "type": "frame",
                        "seq": payload.get("seq"),
                        "data": payload.get("data"),
                        "width": payload.get("width"),
                        "height": payload.get("height"),
                        "ts": payload.get("ts"),
                    })
        except WebSocketDisconnect:
            pass
        finally:
            viewers.discard(ws)
            subs = runtime_state.runs._subscribers.get(run_id, [])
            if queue in subs:
                subs.remove(queue)

    return app


def run_daemon(
    *,
    host: str = DAEMON_HOST,
    port: int = DAEMON_PORT,
    uds: str | None = None,
) -> None:
    from app.worker.cli import _frozen_bootstrap

    _frozen_bootstrap()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    app = create_daemon_app()
    if uds:
        from pathlib import Path

        Path(uds).parent.mkdir(parents=True, exist_ok=True)
        logger.info("desktop runtime listening on unix:%s", uds)
        uvicorn.run(app, uds=uds, log_level="info")
    else:
        logger.info("desktop runtime listening on http://%s:%s", host, port)
        uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_daemon()
