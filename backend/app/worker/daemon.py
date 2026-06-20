"""Desktop runtime sidecar: localhost HTTP API + worker WebSocket."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.schemas import Workflow
from app.worker import credentials as cred_svc
from app.worker import drafts as draft_svc
from app.worker import publish_queue as publish_queue_svc
from app.worker import preflight
from app.worker.cli import AGENT_VERSION, _fetch_worker_status, _run_worker_loop
from app.worker.local_llm import apply_local_config, load_config, public_config, save_config
from app.worker.local_runs import LocalRunManager, cloud_get, cloud_post, fetch_cloud_workflow


logger = logging.getLogger(__name__)

DAEMON_HOST = "127.0.0.1"
DAEMON_PORT = 3921


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


class PublishBody(BaseModel):
    workflow: dict[str, Any]
    authored_by: str = "manual"


@dataclass
class DaemonState:
    approval_status: str = "unknown"
    connected: bool = False
    logged_in: bool = False
    cloud_url: Optional[str] = None
    worker_id: Optional[str] = None
    environment: dict[str, Any] = field(default_factory=dict)
    runs: LocalRunManager = field(default_factory=LocalRunManager)
    _ws_task: Optional[asyncio.Task[None]] = None
    _status_task: Optional[asyncio.Task[None]] = None
    _stream_viewers: dict[str, set[WebSocket]] = field(default_factory=dict)

    def refresh_credentials(self) -> None:
        saved = cred_svc.load_credentials()
        if not saved:
            self.logged_in = False
            self.cloud_url = None
            self.worker_id = None
            self.approval_status = "unknown"
            return
        self.logged_in = True
        self.cloud_url = str(saved.get("cloud_url") or "").rstrip("/") or None
        self.worker_id = saved.get("worker_id")

    def status_payload(self) -> dict[str, Any]:
        env_status = self.environment.get("environment_status", "unknown")
        return {
            "approval_status": self.approval_status,
            "connected": self.connected,
            "logged_in": self.logged_in,
            "cloud_url": self.cloud_url,
            "worker_id": self.worker_id,
            "agent_version": AGENT_VERSION,
            "llm_configured": bool(load_config()),
            "preflight": {
                "environment_status": env_status,
                "checks": self.environment.get("checks", []),
            },
        }


async def _poll_worker_status(state: DaemonState) -> None:
    while True:
        state.refresh_credentials()
        cloud_url = state.cloud_url
        saved = cred_svc.load_credentials()
        token = (saved or {}).get("worker_session_token")
        if cloud_url and token:
            status = await asyncio.to_thread(_fetch_worker_status, cloud_url, token)
            if status is not None:
                state.approval_status = str(
                    status.get("approval_status", state.approval_status)
                )
        await asyncio.sleep(10)


async def _run_preflight(state: DaemonState) -> None:
    cloud_url = state.cloud_url or ""
    try:
        state.environment = await preflight.run_doctor(cloud_url or None)
    except Exception as exc:
        logger.warning("preflight failed: %s", exc)
        state.environment = {
            "environment_status": "unknown",
            "checks": [],
            "error": str(exc),
        }


async def _restart_worker_ws(state: DaemonState) -> None:
    if state._ws_task is not None:
        state._ws_task.cancel()
        try:
            await state._ws_task
        except asyncio.CancelledError:
            pass
    state.connected = False
    state._ws_task = asyncio.create_task(_worker_ws_loop(state))


async def _worker_ws_loop(state: DaemonState) -> None:
    while True:
        state.refresh_credentials()
        saved = cred_svc.load_credentials()
        cloud_url = state.cloud_url
        token = (saved or {}).get("worker_session_token")
        if not cloud_url or not token:
            state.connected = False
            await asyncio.sleep(2)
            continue

        status = await asyncio.to_thread(_fetch_worker_status, cloud_url, token)
        if status is None:
            state.connected = False
            await asyncio.sleep(5)
            continue

        state.approval_status = str(status.get("approval_status", "unknown"))
        if state.approval_status == "rejected":
            state.connected = False
            await asyncio.sleep(10)
            continue

        await _run_preflight(state)
        apply_local_config()

        try:
            logger.info("connecting worker websocket to %s", cloud_url)
            state.connected = True
            await _run_worker_loop(cloud_url, token, state.environment)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("worker websocket disconnected: %s", exc)
        finally:
            state.connected = False
        await asyncio.sleep(3)


async def _flush_publish_queue(state: DaemonState) -> None:
    state.refresh_credentials()
    if state.approval_status != "approved":
        return

    def _publish_local(local_id: str) -> Any:
        draft = draft_svc.get_draft(local_id)
        if draft is None:
            publish_queue_svc.dequeue(local_id)
            raise ValueError("draft not found")
        workflow_id = draft.get("workflow_id")
        if not workflow_id:
            publish_queue_svc.dequeue(local_id)
            raise ValueError("draft not linked to cloud workflow")
        version = cloud_post(
            f"/api/workflows/{workflow_id}/versions",
            {
                "workflow": draft.get("draft_json"),
                "authored_by": "manual",
            },
        )
        draft_svc.save_draft(
            draft_json=draft.get("draft_json") or {},
            local_id=local_id,
            workflow_id=workflow_id,
            name=draft.get("name"),
            cloud_version_id=version.get("id"),
        )
        return version

    try:
        count = await asyncio.to_thread(
            publish_queue_svc.flush_queue,
            publish_fn=_publish_local,
            approval_status=state.approval_status,
        )
        if count:
            logger.info("flushed %s queued publish(es)", count)
    except Exception as exc:
        logger.warning("publish queue flush failed: %s", exc)


def _publish_draft_now(runtime_state: DaemonState, local_id: str) -> dict[str, Any]:
    draft = draft_svc.get_draft(local_id)
    if draft is None:
        raise HTTPException(404, detail="draft not found")
    workflow_id = draft.get("workflow_id")
    if not workflow_id:
        raise HTTPException(
            400,
            detail="draft is not linked to a cloud workflow; pull from cloud first",
        )
    runtime_state.refresh_credentials()
    if runtime_state.approval_status != "approved":
        raise HTTPException(
            403,
            detail="worker not approved; publish is blocked until an admin approves this device",
        )
    version = cloud_post(
        f"/api/workflows/{workflow_id}/versions",
        {
            "workflow": draft.get("draft_json"),
            "authored_by": "manual",
        },
    )
    draft_svc.save_draft(
        draft_json=draft.get("draft_json") or {},
        local_id=local_id,
        workflow_id=workflow_id,
        name=draft.get("name"),
        cloud_version_id=version.get("id"),
    )
    publish_queue_svc.dequeue(local_id)
    return version


def create_daemon_app(state: Optional[DaemonState] = None) -> FastAPI:
    runtime_state = state or DaemonState()
    runtime_state.refresh_credentials()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        runtime_state.refresh_credentials()
        apply_local_config()
        await _run_preflight(runtime_state)
        runtime_state._status_task = asyncio.create_task(
            _poll_worker_status(runtime_state)
        )
        runtime_state._ws_task = asyncio.create_task(
            _worker_ws_loop(runtime_state)
        )
        await _flush_publish_queue(runtime_state)
        yield
        for task in (runtime_state._ws_task, runtime_state._status_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    app = FastAPI(title="Auto Agent Desktop Runtime", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict[str, Any]:
        cloud_url = (runtime_state.cloud_url or "http://127.0.0.1:8001").rstrip("/")
        cloud_ok = False
        try:
            with httpx.Client(timeout=2.0, trust_env=False) as client:
                res = client.get(f"{cloud_url}/api/health")
                cloud_ok = res.status_code == 200
        except Exception:
            cloud_ok = False
        status = "ok" if cloud_ok else "degraded"
        return {"status": status, "cloud": cloud_ok, "sidecar": True}

    @app.get("/status")
    def status() -> dict[str, Any]:
        runtime_state.refresh_credentials()
        return runtime_state.status_payload()

    @app.post("/session")
    async def save_session(body: SessionBody) -> dict[str, str]:
        cred_svc.save_credentials(
            cloud_url=body.cloud_url,
            worker_session_token=body.worker_session_token,
            worker_id=body.worker_id,
            org_id=body.org_id,
            web_session_token=body.web_session_token,
        )
        runtime_state.refresh_credentials()
        saved = cred_svc.load_credentials() or {}
        token = saved.get("worker_session_token")
        cloud_url = runtime_state.cloud_url
        if cloud_url and token:
            status = _fetch_worker_status(cloud_url, token)
            if status is not None:
                runtime_state.approval_status = str(
                    status.get("approval_status", runtime_state.approval_status)
                )
        await _restart_worker_ws(runtime_state)
        return {"status": "saved"}

    @app.delete("/session")
    async def clear_session() -> dict[str, str]:
        cred_svc.clear_credentials()
        runtime_state.refresh_credentials()
        runtime_state.connected = False
        await _restart_worker_ws(runtime_state)
        return {"status": "cleared"}

    @app.get("/settings/llm")
    def get_llm_settings() -> dict[str, Any]:
        return public_config()

    @app.put("/settings/llm")
    def put_llm_settings(body: dict[str, Any]) -> dict[str, Any]:
        current = load_config()
        merged = dict(current)
        for key, val in body.items():
            if isinstance(val, str) and val.startswith("***"):
                continue
            merged[key] = val
        save_config(merged)
        apply_local_config()
        return public_config()

    @app.get("/cloud/workflows")
    def list_cloud_workflows() -> Any:
        try:
            return cloud_get("/api/workflows")
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/cloud/workflows/{workflow_id}")
    def get_cloud_workflow(workflow_id: str) -> Any:
        try:
            return cloud_get(f"/api/workflows/{workflow_id}")
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/cloud/workflows/{workflow_id}/pull")
    def pull_cloud_workflow(workflow_id: str) -> dict[str, Any]:
        try:
            data = cloud_get(f"/api/workflows/{workflow_id}")
            version = data.get("current_version") or {}
            workflow = version.get("workflow")
            if not isinstance(workflow, dict):
                raise HTTPException(404, detail="workflow has no current version")
            draft = draft_svc.pull_from_cloud(
                workflow_id=workflow_id,
                workflow_json=workflow,
                name=str(data.get("name") or workflow_id),
            )
            return draft
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/drafts")
    def list_drafts() -> list[dict[str, Any]]:
        return draft_svc.list_drafts()

    @app.get("/drafts/{local_id}")
    def get_draft(local_id: str) -> dict[str, Any]:
        draft = draft_svc.get_draft(local_id)
        if draft is None:
            raise HTTPException(404, detail="draft not found")
        return draft

    @app.post("/drafts")
    def save_draft(body: DraftSaveBody) -> dict[str, Any]:
        return draft_svc.save_draft(
            draft_json=body.draft_json,
            local_id=body.local_id,
            workflow_id=body.workflow_id,
            name=body.name,
        )

    @app.post("/drafts/{local_id}/publish")
    def publish_draft(local_id: str) -> JSONResponse:
        try:
            version = _publish_draft_now(runtime_state, local_id)
            return JSONResponse(version)
        except HTTPException:
            raise
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail=str(exc)) from exc
        except (httpx.RequestError, RuntimeError) as exc:
            draft = draft_svc.get_draft(local_id)
            if draft is None:
                raise HTTPException(404, detail="draft not found") from exc
            workflow_id = draft.get("workflow_id")
            if not workflow_id:
                raise HTTPException(400, detail="draft not linked to cloud workflow") from exc
            if runtime_state.approval_status != "approved":
                raise HTTPException(
                    403,
                    detail="worker not approved; publish is blocked until an admin approves this device",
                ) from exc
            row = publish_queue_svc.enqueue(
                local_id=local_id,
                workflow_id=str(workflow_id),
                name=draft.get("name"),
            )
            return JSONResponse(
                {
                    "status": "queued",
                    "local_id": local_id,
                    "workflow_id": workflow_id,
                    "queued_at": row.get("queued_at"),
                    "detail": "offline or cloud unreachable; publish queued for retry",
                },
                status_code=202,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/publish-queue")
    def get_publish_queue() -> list[dict[str, Any]]:
        return publish_queue_svc.list_queue()

    @app.post("/publish-queue/retry")
    async def retry_publish_queue() -> dict[str, Any]:
        await _flush_publish_queue(runtime_state)
        return {"queued": len(publish_queue_svc.list_queue())}

    @app.get("/runs")
    def list_runs() -> list[dict[str, Any]]:
        return runtime_state.runs.list_runs()

    @app.post("/runs")
    async def start_run(body: RunStartBody) -> JSONResponse:
        runtime_state.refresh_credentials()
        if not runtime_state.logged_in:
            raise HTTPException(status_code=401, detail="not logged in")
        if runtime_state.approval_status != "approved":
            raise HTTPException(
                status_code=403,
                detail="worker not approved; runs are blocked until an admin approves this device",
            )
        workflow: Workflow | None = None
        workflow_id = body.workflow_id
        if body.workflow is not None:
            workflow = Workflow.model_validate(body.workflow)
        elif workflow_id:
            saved = cred_svc.load_credentials() or {}
            web_token = saved.get("web_session_token")
            cloud_url = runtime_state.cloud_url
            if not cloud_url or not web_token:
                raise HTTPException(
                    400,
                    detail="web session required to fetch workflow by id; sign in again",
                )
            try:
                workflow, workflow_id = await asyncio.to_thread(
                    fetch_cloud_workflow,
                    cloud_url=cloud_url,
                    web_token=str(web_token),
                    workflow_id=workflow_id,
                )
            except Exception as exc:
                raise HTTPException(502, detail=str(exc)) from exc
        else:
            raise HTTPException(400, detail="workflow_id or workflow is required")

        try:
            meta = await runtime_state.runs.start_run(
                workflow=workflow,
                workflow_id=workflow_id,
                parameters=body.parameters,
                trigger_namespace=body.trigger_namespace,
            )
        except RuntimeError as exc:
            raise HTTPException(400, detail=str(exc)) from exc
        return JSONResponse(meta, status_code=201)

    @app.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        row = runtime_state.runs.get_run(run_id)
        if row is None:
            raise HTTPException(404, detail="run not found")
        return row

    @app.post("/runs/{run_id}/abort")
    async def abort_run(run_id: str) -> dict[str, str]:
        ok = await runtime_state.runs.abort_run(run_id)
        if not ok:
            raise HTTPException(404, detail="run not found or not active")
        return {"status": "abort_requested"}

    @app.get("/runs/{run_id}/events")
    async def run_events(run_id: str) -> StreamingResponse:
        if runtime_state.runs.get_run(run_id) is None:
            raise HTTPException(404, detail="run not found")

        async def event_stream():
            async for payload in runtime_state.runs.subscribe_events(run_id):
                if payload is None:
                    yield "event: end\ndata: {}\n\n"
                    break
                if payload.get("type") == "stream_frame":
                    continue
                yield f"data: {json.dumps(payload, default=str)}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

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


def run_daemon(*, host: str = DAEMON_HOST, port: int = DAEMON_PORT) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    app = create_daemon_app()
    logger.info("desktop runtime sidecar listening on http://%s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_daemon()
