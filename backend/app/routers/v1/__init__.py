"""Versioned public API surface (authenticated)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.api_key import require_api_key
from app.routers.v1 import (
    credentials,
    internal_llm,
    keys,
    run_task,
    runs,
    worker_run_files,
    workers,
    workers_ws,
    workflows,
)


v1_router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(require_api_key)],
)

# Keys router manages its own auth (bootstrap on first POST).
v1_keys_router = APIRouter(prefix="/api/v1")
v1_keys_router.include_router(keys.router)

# Worker login/connect use worker session auth, not API keys.
v1_workers_router = APIRouter(prefix="/api/v1")
v1_workers_router.include_router(workers.router)
v1_workers_router.include_router(worker_run_files.router)
v1_workers_router.include_router(workers_ws.router)
v1_workers_router.include_router(internal_llm.router)

v1_router.include_router(run_task.router)
v1_router.include_router(runs.router)
v1_router.include_router(workflows.router)
v1_router.include_router(credentials.router)

__all__ = ["v1_router", "v1_keys_router", "v1_workers_router"]
