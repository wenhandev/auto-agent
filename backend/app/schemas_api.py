from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from app.schemas import Edge, Node, Workflow


class _ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class WorkflowCreate(_ApiModel):
    name: str
    description: Optional[str] = None


class WorkflowUpdate(_ApiModel):
    name: Optional[str] = None
    description: Optional[str] = None


class WorkflowVersionOut(_ApiModel):
    id: str
    workflow_id: str
    version_index: int
    authored_by: Literal["planner", "editor", "manual"]
    workflow: Workflow
    created_at: datetime


class WorkflowOut(_ApiModel):
    id: str
    name: str
    description: Optional[str]
    current_version: Optional[WorkflowVersionOut]
    chat_session_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class WorkflowListItem(_ApiModel):
    id: str
    name: str
    description: Optional[str]
    current_version_index: Optional[int]
    last_run_status: Optional[
        Literal["queued", "running", "completed", "failed", "aborted"]
    ]
    updated_at: datetime


class PatchAddNode(_ApiModel):
    op: Literal["add_node"]
    node: Node


class PatchRemoveNode(_ApiModel):
    op: Literal["remove_node"]
    id: str


class PatchUpdateNode(_ApiModel):
    op: Literal["update_node"]
    id: str
    patch: dict[str, Any]


class PatchAddEdge(_ApiModel):
    op: Literal["add_edge"]
    edge: Edge


class PatchRemoveEdge(_ApiModel):
    op: Literal["remove_edge"]
    id: str


class PatchSetStart(_ApiModel):
    op: Literal["set_start"]
    id: str


PatchOp = Annotated[
    Union[
        PatchAddNode,
        PatchRemoveNode,
        PatchUpdateNode,
        PatchAddEdge,
        PatchRemoveEdge,
        PatchSetStart,
    ],
    Field(discriminator="op"),
]


class ChatTurnRequest(_ApiModel):
    message: str


class ChatMessageOut(_ApiModel):
    id: str
    session_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    workflow_version_id: Optional[str]
    created_at: datetime


class ChatTurnResponse(_ApiModel):
    assistant_message: ChatMessageOut
    patch: Optional[list[PatchOp]] = None
    new_version: Optional[WorkflowVersionOut] = None


class RunCreate(_ApiModel):
    pass


RunStatus = Literal["queued", "running", "completed", "failed", "aborted"]


class RunOut(_ApiModel):
    id: str
    workflow_id: str
    workflow_version_id: str
    status: RunStatus
    queued_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    error: Optional[str]
    source: str = "manual"
    trigger_id: Optional[str] = None
    trigger_context: Optional[dict[str, Any]] = None


class RunEventOut(_ApiModel):
    id: int
    run_id: str
    seq: int
    event_type: str
    node_id: Optional[str]
    ts: datetime
    payload: dict[str, Any]


class RunListItem(_ApiModel):
    id: str
    workflow_id: str
    workflow_name: str
    workflow_version_id: str
    version_index: int
    status: RunStatus
    queued_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    duration_ms: Optional[int]
    error_summary: Optional[str]


class RunReplayResponse(_ApiModel):
    run: RunOut
    workflow_version: WorkflowVersionOut
    events: list[RunEventOut]


class CredentialCreate(_ApiModel):
    name: str
    description: Optional[str] = None
    fields: dict[str, str]


class CredentialUpdate(_ApiModel):
    name: Optional[str] = None
    description: Optional[str] = None
    fields: Optional[dict[str, str]] = None


class CredentialFieldMasked(_ApiModel):
    name: str
    masked_value: str


class CredentialOut(_ApiModel):
    id: str
    name: str
    description: Optional[str]
    fields: list[CredentialFieldMasked]
    created_at: datetime
    updated_at: datetime


class CredentialListItem(_ApiModel):
    id: str
    name: str
    description: Optional[str]
    field_names: list[str]
    updated_at: datetime
    usage_count: int = 0


class WorkflowCredentialLinkRequest(_ApiModel):
    credential_id: str


class LlmConfigUpsert(_ApiModel):
    provider: str
    model: str
    api_key: str
    base_url: Optional[str] = None
    self_healing_enabled: Optional[bool] = None
    self_healing_vision_threshold: Optional[float] = Field(
        default=None, ge=0.0, le=1.0
    )


class LlmConfigOut(_ApiModel):
    id: str
    provider: str
    model: str
    api_key_masked: str
    base_url: Optional[str]
    is_active: bool
    self_healing_enabled: bool
    self_healing_vision_threshold: float
    created_at: datetime
    updated_at: datetime


class LlmEffectiveOut(_ApiModel):
    source: Literal["db", "env"]
    provider: str
    model: str
    api_key_masked: str
    base_url: Optional[str]


class WSStartFrame(_ApiModel):
    type: Literal["start"]
    run_id: Optional[str] = None
    workflow: Optional[Workflow] = None


class WSAbortFrame(_ApiModel):
    type: Literal["abort"]
    run_id: Optional[str] = None


WSClientFrame = Annotated[
    Union[WSStartFrame, WSAbortFrame],
    Field(discriminator="type"),
]


class WSEvent(_ApiModel):
    event: str
    run_id: Optional[str] = None
    node_id: Optional[str] = None
    seq: Optional[int] = None
    ts: str
    message: Optional[str] = None
    output: Optional[Any] = None
    error: Optional[str] = None


__all__ = [
    "WorkflowCreate",
    "WorkflowUpdate",
    "WorkflowOut",
    "WorkflowVersionOut",
    "WorkflowListItem",
    "ChatTurnRequest",
    "ChatTurnResponse",
    "ChatMessageOut",
    "PatchOp",
    "PatchAddNode",
    "PatchRemoveNode",
    "PatchUpdateNode",
    "PatchAddEdge",
    "PatchRemoveEdge",
    "PatchSetStart",
    "RunCreate",
    "RunOut",
    "RunEventOut",
    "RunListItem",
    "RunReplayResponse",
    "RunStatus",
    "CredentialCreate",
    "CredentialUpdate",
    "CredentialOut",
    "CredentialListItem",
    "CredentialFieldMasked",
    "WorkflowCredentialLinkRequest",
    "LlmConfigUpsert",
    "LlmConfigOut",
    "LlmEffectiveOut",
    "WSStartFrame",
    "WSAbortFrame",
    "WSClientFrame",
    "WSEvent",
]


# === triggers-and-scheduling additions ===

TriggerType = Literal["cron", "webhook", "manual"]
TriggerAuthMode = Literal["query_secret", "hmac"]


class TriggerCreate(_ApiModel):
    type: TriggerType
    schedule_or_path: Optional[str] = None
    enabled: bool = True


class TriggerUpdate(_ApiModel):
    enabled: Optional[bool] = None
    schedule_or_path: Optional[str] = None
    regenerate_secret: bool = False


class TriggerOut(_ApiModel):
    id: str
    workflow_id: str
    type: TriggerType
    schedule_or_path: str
    enabled: bool
    auth_mode: TriggerAuthMode
    last_fired_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    webhook_url: Optional[str] = None
    secret_masked: Optional[str] = None
    secret_full: Optional[str] = None


class WebhookFireResponse(_ApiModel):
    run_id: str
    status: Literal["queued"] = "queued"


__all__ += [
    "TriggerType",
    "TriggerAuthMode",
    "TriggerCreate",
    "TriggerUpdate",
    "TriggerOut",
    "WebhookFireResponse",
]
