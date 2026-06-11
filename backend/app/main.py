from __future__ import annotations

import asyncio
import json
import logging
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlmodel import Session, select

from app.agents.planner import PlannerAgent
from app.executor import run_workflow
from app.sample import SAMPLE_WORKFLOW
from app.schemas import GenerateWorkflowRequest, Workflow as WorkflowSchema


logger = logging.getLogger(__name__)


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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from app.db.crypto import load_or_create_key
    from app.db.migrations import (
        add_self_heal_columns_if_missing,
        cleanup_credentials_on_first_run,
        ensure_run_trigger_columns,
        self_healing_default_on_first_run,
    )
    from app.db.session import init_db
    from app.services import runs as run_svc
    from app.services import scheduler as scheduler_svc

    init_db()
    load_or_create_key()
    cleanup_credentials_on_first_run()
    add_self_heal_columns_if_missing()
    self_healing_default_on_first_run()
    ensure_run_trigger_columns()
    _seed_sample_if_empty()
    run_svc.set_main_loop(asyncio.get_running_loop())
    scheduler_svc.init_scheduler(_app)
    try:
        yield
    finally:
        await scheduler_svc.shutdown_scheduler()


app = FastAPI(title="auto-agent backend", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from app.routers.chat import router as chat_router
from app.routers.credentials import router as credentials_router
from app.routers.llm_config import router as llm_config_router
from app.routers.runs import router as runs_router
from app.routers.triggers import router as triggers_router
from app.routers.workflows import router as workflows_router

app.include_router(workflows_router)
app.include_router(chat_router)
app.include_router(runs_router)
app.include_router(credentials_router)
app.include_router(llm_config_router)
app.include_router(triggers_router)


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True}


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
