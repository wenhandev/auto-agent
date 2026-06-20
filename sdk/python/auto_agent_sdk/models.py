from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

RunStatus = Literal[
    "queued",
    "running",
    "completed",
    "completed_with_errors",
    "failed",
    "aborted",
    "rejected",
]

TERMINAL_RUN_STATUSES: frozenset[str] = frozenset(
    {
        "completed",
        "completed_with_errors",
        "failed",
        "aborted",
        "rejected",
    }
)


class _SdkModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class RunTaskRequest(_SdkModel):
    prompt: str = Field(min_length=1)
    url: Optional[str] = None
    data_schema: Optional[dict[str, Any]] = None
    browser_session_id: Optional[str] = None
    browser_profile_id: Optional[str] = None
    totp_identifier: Optional[str] = None
    max_steps: int = Field(default=8, ge=1, le=200)
    persist: bool = True


class RunTaskResponse(_SdkModel):
    run_id: str
    status: RunStatus


class RunCreate(_SdkModel):
    browser_profile_id: Optional[str] = None
    browser_session_id: Optional[str] = None
    parameters: Optional[dict[str, Any]] = None
    totp_identifier: Optional[str] = None
    record_video: Optional[bool] = None


class PendingApproval(_SdkModel):
    node_id: str
    prompt: str
    inputs_schema: list[dict[str, Any]] = Field(default_factory=list)
    requested_at: datetime


class RunOut(_SdkModel):
    id: str
    workflow_id: str
    workflow_version_id: str
    status: RunStatus
    mode: Literal["graph", "autonomous"] = "graph"
    queued_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    source: str = "manual"
    trigger_id: Optional[str] = None
    trigger_context: Optional[dict[str, Any]] = None
    parameters: Optional[dict[str, Any]] = None
    artifact_counts: dict[str, int] = Field(default_factory=dict)
    browser_profile_id: Optional[str] = None
    browser_session_id: Optional[str] = None
    totp_identifier: Optional[str] = None
    pending_approval: Optional[PendingApproval] = None
    queue_position: Optional[int] = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_llm_calls: int = 0
    total_vision_calls: int = 0
    estimated_cost_usd: Optional[float] = None
    cost_note: Optional[str] = None
    usage_summary: Optional[dict[str, Any]] = None
    node_costs: list[dict[str, Any]] = Field(default_factory=list)


class RunEventOut(_SdkModel):
    id: int
    run_id: str
    seq: int
    event_type: str
    node_id: Optional[str] = None
    ts: datetime
    payload: dict[str, Any]


class WorkflowVersionOut(_SdkModel):
    id: str
    workflow_id: str
    version_index: int
    authored_by: Literal["planner", "editor", "manual"]
    workflow: dict[str, Any]
    created_at: datetime


class RunReplayResponse(_SdkModel):
    run: RunOut
    workflow_version: WorkflowVersionOut
    events: list[RunEventOut]


class RunListItem(_SdkModel):
    id: str
    workflow_id: str
    workflow_name: str
    workflow_version_id: str
    version_index: int
    status: RunStatus
    queued_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    error_summary: Optional[str] = None
    pending_approval: Optional[PendingApproval] = None
    queue_position: Optional[int] = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_llm_calls: int = 0
    total_vision_calls: int = 0
    estimated_cost_usd: Optional[float] = None
    cost_note: Optional[str] = None


class RunListPage(_SdkModel):
    items: list[RunListItem]
    next_cursor: Optional[str] = None


class WorkflowListItem(_SdkModel):
    id: str
    name: str
    description: Optional[str] = None
    current_version_index: Optional[int] = None
    last_run_status: Optional[RunStatus] = None
    updated_at: datetime


class CredentialListItem(_SdkModel):
    id: str
    name: str
    type: str = "generic"
    description: Optional[str] = None
    field_names: list[str]
    updated_at: datetime
    usage_count: int = 0


__all__ = [
    "TERMINAL_RUN_STATUSES",
    "CredentialListItem",
    "PendingApproval",
    "RunCreate",
    "RunEventOut",
    "RunListItem",
    "RunListPage",
    "RunOut",
    "RunReplayResponse",
    "RunStatus",
    "RunTaskRequest",
    "RunTaskResponse",
    "WorkflowListItem",
    "WorkflowVersionOut",
]
