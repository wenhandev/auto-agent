"""Python client for the auto-agent /api/v1 public API."""

from auto_agent_sdk.async_client import AsyncAutoAgent
from auto_agent_sdk.client import AutoAgent
from auto_agent_sdk.models import (
    RunCreate,
    RunListItem,
    RunListPage,
    RunOut,
    RunReplayResponse,
    RunStatus,
    RunTaskRequest,
    RunTaskResponse,
    WorkflowListItem,
)

# Ergonomic aliases matching common SDK naming (AutoAgent remains canonical).
Client = AutoAgent
AsyncClient = AsyncAutoAgent

__all__ = [
    "AsyncAutoAgent",
    "AsyncClient",
    "AutoAgent",
    "Client",
    "RunCreate",
    "RunListItem",
    "RunListPage",
    "RunOut",
    "RunReplayResponse",
    "RunStatus",
    "RunTaskRequest",
    "RunTaskResponse",
    "WorkflowListItem",
]
