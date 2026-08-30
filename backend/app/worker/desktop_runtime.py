"""Shared desktop runtime state and background tasks (HTTP daemon + message host)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.worker import credentials as cred_svc
from app.worker import drafts as draft_svc
from app.worker import publish_queue as publish_queue_svc
from app.worker import preflight
from app.worker.cli import AGENT_VERSION, _fetch_worker_status, _run_worker_loop
from app.worker.local_llm import apply_local_config, load_config
from app.worker.local_runs import LocalRunManager, cloud_post


logger = logging.getLogger(__name__)

DAEMON_HOST = "127.0.0.1"
DAEMON_PORT = 3921


@dataclass
class DesktopRuntime:
    approval_status: str = "unknown"
    connected: bool = False
    logged_in: bool = False
    cloud_url: Optional[str] = None
    worker_id: Optional[str] = None
    environment: dict[str, Any] = field(default_factory=dict)
    runs: LocalRunManager = field(default_factory=LocalRunManager)
    _ws_task: Optional[asyncio.Task[None]] = None
    _status_task: Optional[asyncio.Task[None]] = None
    _stream_viewers: dict[str, set[Any]] = field(default_factory=dict)

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


# Backwards compatibility for tests and imports.
DaemonState = DesktopRuntime


async def poll_worker_status(state: DesktopRuntime) -> None:
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


async def run_preflight(state: DesktopRuntime) -> None:
    cloud_url = state.cloud_url or ""
    try:
        state.environment = await preflight.run_doctor(
            cloud_url or None,
            agent_version=AGENT_VERSION,
        )
    except Exception as exc:
        logger.warning("preflight failed: %s", exc)
        state.environment = {
            "environment_status": "unknown",
            "checks": [],
            "error": str(exc),
        }


async def bootstrap_environment(state: DesktopRuntime) -> None:
    try:
        local = await preflight.ensure_chromium_installed()
        chromium = next(
            (c for c in local.get("checks", []) if c.get("id") == "chromium_binary"),
            None,
        )
        if chromium and chromium.get("status") != "pass":
            logger.warning("chromium still missing after install attempt")
    except Exception as exc:
        logger.warning("chromium bootstrap failed: %s", exc)
    await run_preflight(state)


async def restart_worker_ws(state: DesktopRuntime) -> None:
    if state._ws_task is not None:
        state._ws_task.cancel()
        try:
            await state._ws_task
        except asyncio.CancelledError:
            pass
    state.connected = False
    state._ws_task = asyncio.create_task(worker_ws_loop(state))


async def worker_ws_loop(state: DesktopRuntime) -> None:
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

        await run_preflight(state)
        apply_local_config()

        try:
            from app.worker.llm_proxy import install_llm_proxy

            install_llm_proxy(cloud_url=cloud_url, token=token)
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


async def flush_publish_queue(state: DesktopRuntime) -> None:
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


async def start_background_tasks(state: DesktopRuntime) -> None:
    state.refresh_credentials()
    apply_local_config()
    await bootstrap_environment(state)
    state._status_task = asyncio.create_task(poll_worker_status(state))
    state._ws_task = asyncio.create_task(worker_ws_loop(state))
    await flush_publish_queue(state)


async def stop_background_tasks(state: DesktopRuntime) -> None:
    for task in (state._ws_task, state._status_task):
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
