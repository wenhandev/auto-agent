from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles
from pydantic import ValidationError
from sqlmodel import Session, select

from app.agents.planner import PlannerAgent
from app.executor import run_workflow
from app.sample import SAMPLE_WORKFLOW
from app.schemas import GenerateWorkflowRequest, Workflow as WorkflowSchema


logger = logging.getLogger(__name__)


class SPAStaticFiles(StaticFiles):
    """Serve the built SPA; unknown non-file paths fall back to index.html."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            leaf = path.rsplit("/", 1)[-1]
            if leaf and "." in leaf:
                raise
            return await super().get_response("index.html", scope)


def _seed_sample_if_empty() -> None:
    from app.db.models import Workflow
    from app.db.session import engine
    from app.services import workflows as workflow_svc

    with Session(engine) as session:
        existing = session.exec(select(Workflow)).first()
        if existing is not None:
            return
        wf_json = SAMPLE_WORKFLOW.model_dump()
        workflow_svc.create_workflow(
            name="示例工作流",
            session=session,
            description="自动生成的示例工作流(可直接运行)",
            initial_workflow_json=wf_json,
            authored_by="manual",
        )
        logger.info("seeded sample workflow")


def _seed_apple_workflow_if_missing() -> None:
    from app.db.models import Workflow
    from app.db.session import engine
    from app.services import workflows as workflow_svc
    from app.workflows.apple_new_products import (
        APPLE_NEW_PRODUCTS_WORKFLOW,
        APPLE_WORKFLOW_DESCRIPTION,
        APPLE_WORKFLOW_NAME,
    )

    with Session(engine) as session:
        if session.exec(
            select(Workflow).where(Workflow.name == "Acme Supply Hub Demo")
        ).first():
            return
        existing = session.exec(
            select(Workflow).where(Workflow.name == APPLE_WORKFLOW_NAME)
        ).first()
        if existing is not None:
            return
        workflow_svc.create_workflow(
            name=APPLE_WORKFLOW_NAME,
            session=session,
            description=APPLE_WORKFLOW_DESCRIPTION,
            initial_workflow_json=APPLE_NEW_PRODUCTS_WORKFLOW.model_dump(),
            authored_by="manual",
        )
        logger.info("seeded apple new products workflow")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from app.db.crypto import load_or_create_key
    from app.db.migrations import (
        add_credential_type_column,
        add_parent_run_id_on_first_run,
        add_self_heal_columns_if_missing,
        cleanup_credentials_on_first_run,
        ensure_run_browser_profile_column,
        ensure_run_browser_session_column,
        ensure_browser_session_memory_column,
        ensure_browser_session_provider_columns,
        ensure_run_browser_provider_columns,
        ensure_run_mode_and_task_columns,
        ensure_run_parameters_json_column,
        ensure_run_cost_columns,
        ensure_selector_cache_column,
        ensure_run_totp_identifier_column,
        ensure_run_record_video_column,
        ensure_run_proxy_id_column,
        ensure_browser_profile_antibot_columns,
        ensure_org_columns,
        ensure_workflow_visibility_column,
        bootstrap_orgs_on_startup,
        ensure_worker_tables,
        ensure_run_worker_columns,
        ensure_desktop_client_columns,
        ensure_user_identity_table,
        ensure_user_platform_admin_column,
        ensure_oauth_domain_rule_table,
        ensure_run_trigger_columns,
        ensure_trigger_parameters_json_column,
        ensure_trigger_poll_app_columns,
        ensure_trigger_scheduling_columns,
        ensure_workflow_status_column,
        ensure_workflow_version_parameters_column,
        self_healing_default_on_first_run,
    )
    from app.db.session import init_db
    from app.integrations import load_integrations
    from app.services import runs as run_svc
    from app.services import scheduler as scheduler_svc
    from app.services import artifacts as artifact_svc
    from app.services import browser_profiles as browser_profile_svc
    from app.services import browser_sessions as browser_session_svc
    from app.services import cost_tracking as cost_tracking_svc
    from app.tools.sandbox import ensure_workspace_root

    init_db()
    ensure_org_columns()
    ensure_workflow_visibility_column()
    ensure_user_platform_admin_column()
    bootstrap_orgs_on_startup()
    ensure_worker_tables()
    ensure_desktop_client_columns()
    ensure_oauth_domain_rule_table()
    ensure_user_identity_table()
    ensure_run_worker_columns()
    artifact_svc.ensure_artifact_root()
    browser_profile_svc.ensure_profiles_root()
    artifact_svc.reap_expired_artifacts()
    load_or_create_key()
    cleanup_credentials_on_first_run()
    add_self_heal_columns_if_missing()
    self_healing_default_on_first_run()
    ensure_run_trigger_columns()
    ensure_trigger_poll_app_columns()
    ensure_trigger_scheduling_columns()
    add_parent_run_id_on_first_run()
    add_credential_type_column()
    ensure_run_mode_and_task_columns()
    ensure_run_browser_profile_column()
    ensure_run_browser_session_column()
    ensure_browser_session_memory_column()
    ensure_browser_session_provider_columns()
    ensure_run_browser_provider_columns()
    ensure_workflow_status_column()
    ensure_workflow_version_parameters_column()
    ensure_run_parameters_json_column()
    ensure_run_totp_identifier_column()
    ensure_run_record_video_column()
    ensure_run_cost_columns()
    ensure_selector_cache_column()
    ensure_trigger_parameters_json_column()
    cost_tracking_svc.ensure_model_prices_seeded()
    ensure_workspace_root()
    load_integrations()
    from app.services import approvals as approvals_svc

    approvals_svc.reap_lost_approvals_on_startup()
    browser_session_svc.expire_all_live_on_startup()
    run_svc.fail_in_flight_runs_on_startup()
    _seed_sample_if_empty()
    _seed_apple_workflow_if_missing()
    run_svc.set_main_loop(asyncio.get_running_loop())
    scheduler_svc.init_scheduler(_app)
    from app.services import webhooks as webhooks_svc

    from app.settings import settings

    webhooks_svc.reload_pending_deliveries()
    browser_session_svc.start_reaper()
    try:
        yield
    finally:
        if settings.execution_backend != "control_plane_only":
            from app.tools import browser as browser_tools

            await browser_tools.shutdown()
        else:
            logger.info(
                "execution_backend=control_plane_only — skipping Playwright shutdown"
            )
        await scheduler_svc.shutdown_scheduler()


app = FastAPI(
    title="auto-agent backend",
    version="0.1.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "api-keys", "description": "Manage API keys for programmatic access"},
        {"name": "run-task", "description": "Skyvern-style autonomous run entry point"},
        {"name": "runs", "description": "Run status, listing, and cancellation"},
        {"name": "workflows", "description": "Workflow CRUD and execution"},
        {"name": "recordings", "description": "Browser action recording and workflow generation"},
        {"name": "credentials", "description": "Credential vault (masked responses)"},
        {"name": "webhooks", "description": "Outbound webhook subscriptions"},
    ],
)

from app.settings import cors_origin_list

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from app.routers.approvals import router as approvals_router
from app.routers.browser_profiles import router as browser_profiles_router
from app.routers.browser_sessions import router as browser_sessions_router
from app.routers.route_skills import router as route_skills_router
from app.routers.chat import router as chat_router
from app.routers.credentials import router as credentials_router
from app.routers.expressions import router as expressions_router
from app.routers.integrations import router as integrations_router
from app.routers.llm_config import router as llm_config_router
from app.routers.oauth2 import router as oauth2_router
from app.routers.recordings import router as recordings_router
from app.routers.runs import router as runs_router
from app.routers.tasks import router as tasks_router
from app.routers.triggers import router as triggers_router
from app.routers.webhooks import internal_router as webhooks_internal_router
from app.routers.webhooks import router as webhooks_router
from app.routers.workflows import router as workflows_router
from app.routers.v1 import v1_keys_router, v1_router, v1_workers_router
from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.oauth_login import router as oauth_login_router
from app.routers.orgs import router as orgs_router
from app.routers.workers import router as workers_ui_router
from app.routers.recaptcha_test import router as recaptcha_test_router
from app.routers.settings import router as settings_router

app.include_router(admin_router)
app.include_router(auth_router)
app.include_router(oauth_login_router)
app.include_router(orgs_router)
app.include_router(workflows_router)
app.include_router(recordings_router)
app.include_router(browser_profiles_router)
app.include_router(browser_sessions_router)
app.include_router(route_skills_router)
app.include_router(chat_router)
app.include_router(runs_router)
app.include_router(approvals_router)
app.include_router(credentials_router)
app.include_router(expressions_router)
app.include_router(integrations_router)
app.include_router(oauth2_router)
app.include_router(llm_config_router)
app.include_router(triggers_router)
app.include_router(tasks_router)
app.include_router(webhooks_router)
app.include_router(webhooks_internal_router)
app.include_router(v1_keys_router)
app.include_router(v1_workers_router)
app.include_router(v1_router)
app.include_router(workers_ui_router)
app.include_router(recaptcha_test_router)
app.include_router(settings_router)

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

_FRONTEND_DIR = Path(
    os.environ.get("FRONTEND_STATIC_DIR", "/srv/frontend")
)


def _custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    from fastapi.openapi.utils import get_openapi

    schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
        tags=app.openapi_tags,
    )
    components = schema.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "description": "API key passed as Bearer token",
    }
    security_schemes["ApiKeyHeader"] = {
        "type": "apiKey",
        "in": "header",
        "name": "x-api-key",
        "description": "API key in x-api-key header",
    }
    for path, methods in schema.get("paths", {}).items():
        if not path.startswith("/api/v1"):
            continue
        if path.startswith("/api/v1/keys") and "post" in methods:
            continue
        for operation in methods.values():
            if isinstance(operation, dict):
                operation["security"] = [
                    {"BearerAuth": []},
                    {"ApiKeyHeader": []},
                ]
    app.openapi_schema = schema
    return schema


app.openapi = _custom_openapi


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True}


@app.get("/demo", include_in_schema=False)
async def demo_portal_redirect() -> RedirectResponse:
    """Redirect to the Acme Supply Hub client demo portal."""
    return RedirectResponse(url="/static/portal/index.html")


@app.get("/api/sample-workflow")
async def sample_workflow() -> dict:
    return SAMPLE_WORKFLOW.model_dump()


@app.post("/api/workflow/generate")
async def generate_workflow(body: GenerateWorkflowRequest) -> dict:
    try:
        workflow = await PlannerAgent().generate_workflow(body.description)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return workflow.model_dump()


async def _stream_platform_run(ws: WebSocket, run_id: str) -> None:
    from app.services import runs as run_svc

    queue = run_svc.subscribe(run_id)
    seen_seqs: set[int] = set()
    try:
        for prior in run_svc.fetch_prior_events(run_id):
            seq = prior.get("seq")
            if isinstance(seq, int):
                seen_seqs.add(seq)
            await ws.send_json(prior)
            if run_svc.is_terminal(prior):
                return

        while True:
            recv_task = asyncio.create_task(ws.receive_text())
            queue_task = asyncio.create_task(queue.get())
            done, pending = await asyncio.wait(
                {recv_task, queue_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if queue_task in done:
                recv_task.cancel()
                try:
                    payload = queue_task.result()
                except Exception:
                    continue
                seq = payload.get("seq")
                if isinstance(seq, int) and seq in seen_seqs:
                    if run_svc.is_terminal(payload):
                        return
                    continue
                if isinstance(seq, int):
                    seen_seqs.add(seq)
                await ws.send_json(payload)
                if run_svc.is_terminal(payload):
                    return
            else:
                queue_task.cancel()
                try:
                    text = recv_task.result()
                except WebSocketDisconnect:
                    return
                except Exception:
                    return
                try:
                    msg = json.loads(text)
                except Exception:
                    continue
                if msg.get("type") == "abort":
                    try:
                        run_svc.request_abort(run_id)
                    except Exception:
                        logger.exception("abort failed run=%s", run_id)
    finally:
        run_svc.unsubscribe(run_id, queue)


@app.websocket("/ws/run")
async def ws_run(ws: WebSocket) -> None:
    await ws.accept()
    try:
        raw = await ws.receive_text()
        try:
            frame = json.loads(raw)
        except Exception as exc:
            await ws.send_json({
                "event": "run_failed",
                "node_id": None,
                "ts": "",
                "error": f"invalid start frame: {exc}",
            })
            await ws.close(code=1003)
            return
        if frame.get("type") != "start":
            await ws.send_json({
                "event": "run_failed",
                "node_id": None,
                "ts": "",
                "error": "first frame must be type=start",
            })
            await ws.close(code=1003)
            return

        run_id = frame.get("run_id")
        if run_id:
            await _stream_platform_run(ws, run_id)
            try:
                await ws.close(code=1000)
            except Exception:
                pass
            return

        wf_payload = frame.get("workflow")
        if not wf_payload:
            await ws.send_json({
                "event": "run_failed",
                "node_id": None,
                "ts": "",
                "error": "start frame requires either run_id or workflow",
            })
            await ws.close(code=1003)
            return
        try:
            workflow = WorkflowSchema.model_validate(wf_payload)
        except ValidationError as exc:
            await ws.send_json({
                "event": "run_failed",
                "node_id": None,
                "ts": "",
                "error": f"invalid workflow: {exc}",
            })
            await ws.close(code=1003)
            return

        async def on_event(payload: dict) -> None:
            await ws.send_json(payload)

        try:
            await run_workflow(workflow, on_event)
        except Exception as exc:
            logger.exception("executor crashed")
            await ws.send_json({
                "event": "run_failed",
                "node_id": None,
                "ts": "",
                "error": str(exc),
            })

        try:
            await ws.close(code=1000)
        except Exception:
            pass
    except WebSocketDisconnect:
        return


@app.websocket("/ws/stream/{run_id}")
async def ws_stream(run_id: str, ws: WebSocket) -> None:
    from app.services import livestream as livestream_svc

    await livestream_svc.handle_connection(run_id, ws)


if _FRONTEND_DIR.is_dir():
    app.mount(
        "/",
        SPAStaticFiles(directory=str(_FRONTEND_DIR), html=True),
        name="frontend",
    )
