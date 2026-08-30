"""Desktop runtime API — shared by HTTP daemon and structured message host."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from app.schemas import Workflow
from app.worker import credentials as cred_svc
from app.worker import drafts as draft_svc
from app.worker import publish_queue as publish_queue_svc
from app.worker import preflight
from app.worker.cli import AGENT_VERSION, _fetch_worker_status
from app.worker.desktop_runtime import DesktopRuntime, restart_worker_ws
from app.worker.local_llm import apply_local_config, load_config, public_config, save_config
from app.worker.local_runs import cloud_get, fetch_cloud_workflow


class DesktopApiError(Exception):
    """Maps to HTTP status when served via FastAPI; maps to protocol error otherwise."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "api_error",
        status: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class DesktopApi:
    def __init__(self, runtime: DesktopRuntime) -> None:
        self.runtime = runtime

    def health(self) -> dict[str, str]:
        return {"status": "ok"}

    def ready(self) -> dict[str, Any]:
        cloud_url = (self.runtime.cloud_url or "http://127.0.0.1:8001").rstrip("/")
        cloud_ok = False
        try:
            with httpx.Client(timeout=2.0, trust_env=False) as client:
                res = client.get(f"{cloud_url}/api/health")
                cloud_ok = res.status_code == 200
        except Exception:
            cloud_ok = False
        status = "ok" if cloud_ok else "degraded"
        return {"status": status, "cloud": cloud_ok, "sidecar": True}

    def get_status(self) -> dict[str, Any]:
        self.runtime.refresh_credentials()
        return self.runtime.status_payload()

    async def run_doctor(self) -> dict[str, Any]:
        cloud_url = self.runtime.cloud_url or ""
        return await preflight.run_doctor(
            cloud_url or None,
            agent_version=AGENT_VERSION,
        )

    async def save_session(self, params: dict[str, Any]) -> dict[str, str]:
        required = ("cloud_url", "worker_session_token", "worker_id", "org_id")
        for key in required:
            if not params.get(key):
                raise DesktopApiError(f"missing {key}", code="invalid_params", status=422)
        cred_svc.save_credentials(
            cloud_url=str(params["cloud_url"]),
            worker_session_token=str(params["worker_session_token"]),
            worker_id=str(params["worker_id"]),
            org_id=str(params["org_id"]),
            web_session_token=params.get("web_session_token"),
        )
        self.runtime.refresh_credentials()
        saved = cred_svc.load_credentials() or {}
        token = saved.get("worker_session_token")
        cloud_url = self.runtime.cloud_url
        if cloud_url and token:
            status = _fetch_worker_status(cloud_url, token)
            if status is not None:
                self.runtime.approval_status = str(
                    status.get("approval_status", self.runtime.approval_status)
                )
        await restart_worker_ws(self.runtime)
        return {"status": "saved"}

    async def clear_session(self) -> dict[str, str]:
        cred_svc.clear_credentials()
        self.runtime.refresh_credentials()
        self.runtime.connected = False
        await restart_worker_ws(self.runtime)
        return {"status": "cleared"}

    def get_llm_settings(self) -> dict[str, Any]:
        return public_config()

    def put_llm_settings(self, body: dict[str, Any]) -> dict[str, Any]:
        current = load_config()
        merged = dict(current)
        for key, val in body.items():
            if isinstance(val, str) and val.startswith("***"):
                continue
            merged[key] = val
        save_config(merged)
        apply_local_config()
        return public_config()

    def get_computer_use_settings(self) -> dict[str, Any]:
        import sys

        from app.services.desktop_computer_use import (
            desktop_computer_use_availability,
            get_auth_store,
        )

        store = get_auth_store()
        available, reason = desktop_computer_use_availability()
        hint = (
            "Grant Screen Recording and Accessibility to Auto Agent "
            "in System Settings → Privacy & Security."
            if sys.platform == "darwin"
            else (
                "On Windows, keep the target app visible on the active desktop. "
                "Install desktop extras: pip install -e '.[desktop-windows]'."
                if sys.platform == "win32"
                else "Desktop Computer Use requires macOS or Windows."
            )
        )
        if reason:
            hint = f"{hint} ({reason})" if hint else reason
        return {
            "available": available,
            "reason": reason,
            "platform": sys.platform,
            "always_allowed": store.list_always_allowed(),
            "system_permissions_hint": hint,
        }

    def put_computer_use_settings(self, body: dict[str, Any]) -> dict[str, Any]:
        from app.services.desktop_computer_use import get_auth_store

        store = get_auth_store()
        allow = body.get("allow_always")
        if isinstance(allow, str) and allow.strip():
            store.allow_always(allow.strip())
        revoke = body.get("revoke")
        if isinstance(revoke, str) and revoke.strip():
            store.revoke(revoke.strip())
        return self.get_computer_use_settings()

    def list_cloud_workflows(self) -> Any:
        try:
            return cloud_get("/api/workflows")
        except Exception as exc:
            raise DesktopApiError(str(exc), code="cloud_error", status=502) from exc

    def get_cloud_workflow(self, workflow_id: str) -> Any:
        try:
            return cloud_get(f"/api/workflows/{workflow_id}")
        except Exception as exc:
            raise DesktopApiError(str(exc), code="cloud_error", status=502) from exc

    def pull_cloud_workflow(self, workflow_id: str) -> dict[str, Any]:
        try:
            data = cloud_get(f"/api/workflows/{workflow_id}")
            version = data.get("current_version") or {}
            workflow = version.get("workflow")
            if not isinstance(workflow, dict):
                raise DesktopApiError(
                    "workflow has no current version",
                    code="not_found",
                    status=404,
                )
            return draft_svc.pull_from_cloud(
                workflow_id=workflow_id,
                workflow_json=workflow,
                name=str(data.get("name") or workflow_id),
            )
        except DesktopApiError:
            raise
        except Exception as exc:
            raise DesktopApiError(str(exc), code="cloud_error", status=502) from exc

    def list_drafts(self) -> list[dict[str, Any]]:
        return draft_svc.list_drafts()

    def get_draft(self, local_id: str) -> dict[str, Any]:
        draft = draft_svc.get_draft(local_id)
        if draft is None:
            raise DesktopApiError("draft not found", code="not_found", status=404)
        return draft

    def save_draft(self, params: dict[str, Any]) -> dict[str, Any]:
        draft_json = params.get("draft_json")
        if not isinstance(draft_json, dict):
            raise DesktopApiError("draft_json required", code="invalid_params", status=422)
        return draft_svc.save_draft(
            draft_json=draft_json,
            local_id=params.get("local_id"),
            workflow_id=params.get("workflow_id"),
            name=params.get("name"),
        )

    def publish_draft(self, local_id: str) -> dict[str, Any]:
        try:
            return self._publish_draft_now(local_id)
        except DesktopApiError:
            raise
        except httpx.HTTPStatusError as exc:
            raise DesktopApiError(
                str(exc),
                code="cloud_http_error",
                status=exc.response.status_code,
            ) from exc
        except (httpx.RequestError, RuntimeError) as exc:
            draft = draft_svc.get_draft(local_id)
            if draft is None:
                raise DesktopApiError("draft not found", code="not_found", status=404) from exc
            workflow_id = draft.get("workflow_id")
            if not workflow_id:
                raise DesktopApiError(
                    "draft not linked to cloud workflow",
                    code="invalid_draft",
                    status=400,
                ) from exc
            if self.runtime.approval_status != "approved":
                raise DesktopApiError(
                    "worker not approved; publish is blocked until an admin approves this device",
                    code="not_approved",
                    status=403,
                ) from exc
            row = publish_queue_svc.enqueue(
                local_id=local_id,
                workflow_id=str(workflow_id),
                name=draft.get("name"),
            )
            return {
                "status": "queued",
                "local_id": local_id,
                "workflow_id": workflow_id,
                "queued_at": row.get("queued_at"),
                "detail": "offline or cloud unreachable; publish queued for retry",
                "_http_status": 202,
            }
        except Exception as exc:
            raise DesktopApiError(str(exc), code="cloud_error", status=502) from exc

    def list_publish_queue(self) -> list[dict[str, Any]]:
        return publish_queue_svc.list_queue()

    async def retry_publish_queue(self) -> dict[str, Any]:
        from app.worker.desktop_runtime import flush_publish_queue

        await flush_publish_queue(self.runtime)
        return {"queued": len(publish_queue_svc.list_queue())}

    def list_runs(self) -> list[dict[str, Any]]:
        return self.runtime.runs.list_runs()

    async def start_run(self, params: dict[str, Any]) -> dict[str, Any]:
        self.runtime.refresh_credentials()
        if not self.runtime.logged_in:
            raise DesktopApiError("not logged in", code="unauthorized", status=401)
        if self.runtime.approval_status != "approved":
            raise DesktopApiError(
                "worker not approved; runs are blocked until an admin approves this device",
                code="not_approved",
                status=403,
            )
        workflow: Workflow | None = None
        workflow_id = params.get("workflow_id")
        inline = params.get("workflow")
        if inline is not None:
            workflow = Workflow.model_validate(inline)
        elif workflow_id:
            saved = cred_svc.load_credentials() or {}
            web_token = saved.get("web_session_token")
            cloud_url = self.runtime.cloud_url
            if not cloud_url or not web_token:
                raise DesktopApiError(
                    "web session required to fetch workflow by id; sign in again",
                    code="invalid_session",
                    status=400,
                )
            try:
                workflow, workflow_id = await asyncio.to_thread(
                    fetch_cloud_workflow,
                    cloud_url=cloud_url,
                    web_token=str(web_token),
                    workflow_id=str(workflow_id),
                )
            except Exception as exc:
                raise DesktopApiError(str(exc), code="cloud_error", status=502) from exc
        else:
            raise DesktopApiError(
                "workflow_id or workflow is required",
                code="invalid_params",
                status=400,
            )

        try:
            meta = await self.runtime.runs.start_run(
                workflow=workflow,
                workflow_id=workflow_id,
                parameters=params.get("parameters") or {},
                trigger_namespace=params.get("trigger_namespace") or {},
            )
        except RuntimeError as exc:
            raise DesktopApiError(str(exc), code="run_error", status=400) from exc
        return {**meta, "_http_status": 201}

    def get_run(self, run_id: str) -> dict[str, Any]:
        row = self.runtime.runs.get_run(run_id)
        if row is None:
            raise DesktopApiError("run not found", code="not_found", status=404)
        return row

    async def abort_run(self, run_id: str) -> dict[str, str]:
        ok = await self.runtime.runs.abort_run(run_id)
        if not ok:
            raise DesktopApiError(
                "run not found or not active",
                code="not_found",
                status=404,
            )
        return {"status": "abort_requested"}

    async def iter_run_events(self, run_id: str):
        if self.runtime.runs.get_run(run_id) is None:
            raise DesktopApiError("run not found", code="not_found", status=404)
        async for payload in self.runtime.runs.subscribe_events(run_id):
            yield payload

    def _publish_draft_now(self, local_id: str) -> dict[str, Any]:
        draft = draft_svc.get_draft(local_id)
        if draft is None:
            raise DesktopApiError("draft not found", code="not_found", status=404)
        workflow_id = draft.get("workflow_id")
        if not workflow_id:
            raise DesktopApiError(
                "draft is not linked to a cloud workflow; pull from cloud first",
                code="invalid_draft",
                status=400,
            )
        self.runtime.refresh_credentials()
        if self.runtime.approval_status != "approved":
            raise DesktopApiError(
                "worker not approved; publish is blocked until an admin approves this device",
                code="not_approved",
                status=403,
            )
        from app.worker.local_runs import cloud_post

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


def sse_event_line(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return "event: end\ndata: {}\n\n"
    if payload.get("type") in ("stream_frame", "frame"):
        return ""
    return f"data: {json.dumps(payload, default=str)}\n\n"
