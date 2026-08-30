from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas import Edge, Node, Workflow


class _ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


RunStatus = Literal[
    "queued",
    "running",
    "completed",
    "completed_with_errors",
    "failed",
    "aborted",
    "rejected",
]


class WorkflowCreate(_ApiModel):
    name: str
    description: Optional[str] = None


class WorkflowUpdate(_ApiModel):
    name: Optional[str] = None
    description: Optional[str] = None


class WorkflowVersionCreate(_ApiModel):
    workflow: Workflow
    authored_by: Literal["planner", "editor", "manual"] = "manual"


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
    last_run_status: Optional[RunStatus] = None
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


class ViewportSpec(_ApiModel):
    width: int = Field(default=1280, ge=1)
    height: int = Field(default=720, ge=1)


class BrowserProfileCreate(_ApiModel):
    name: str
    user_agent: Optional[str] = None
    viewport: Optional[ViewportSpec] = None
    persist_cookies: bool = True
    persist_local_storage: bool = True


class BrowserProfileUpdate(_ApiModel):
    name: Optional[str] = None
    user_agent: Optional[str] = None
    viewport: Optional[ViewportSpec] = None
    persist_cookies: Optional[bool] = None
    persist_local_storage: Optional[bool] = None


class BrowserProfileOut(_ApiModel):
    id: str
    name: str
    user_agent: Optional[str] = None
    viewport: Optional[ViewportSpec] = None
    persist_cookies: bool = True
    persist_local_storage: bool = True
    has_storage_state: bool = False
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime] = None


BrowserSessionStatus = Literal["live", "idle", "closed", "expired"]


class BrowserSessionCreate(_ApiModel):
    profile_id: Optional[str] = None
    provider_id: Optional[str] = None
    provider_config: Optional[dict[str, Any]] = None


class BrowserSessionOut(_ApiModel):
    id: str
    profile_id: Optional[str] = None
    status: BrowserSessionStatus
    started_at: datetime
    expires_at: datetime
    last_activity_at: datetime
    seconds_until_expiry: Optional[int] = None
    provider_id: str = "local_playwright"
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class PickerEnableIn(_ApiModel):
    mode: str = "coordinate"


class PickerEnableOut(_ApiModel):
    picker_token: str
    mode: str


class PickerDisableIn(_ApiModel):
    picker_token: str


class SessionNavigateIn(_ApiModel):
    url: str
    picker_token: str


class SessionNavigateOut(_ApiModel):
    url: str
    title: str = ""


class PickElementIn(_ApiModel):
    x: float
    y: float
    picker_token: str


class SelectorCandidateOut(_ApiModel):
    selector: str
    strategy: str
    confidence: float
    match_count: int = 0


class ElementSummaryOut(_ApiModel):
    tag: Optional[str] = None
    role: Optional[str] = None
    name: Optional[str] = None
    text: Optional[str] = None


class PickElementOut(_ApiModel):
    candidates: list[SelectorCandidateOut] = Field(default_factory=list)
    element_summary: Optional[ElementSummaryOut] = None
    viewport: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class TestSelectorIn(_ApiModel):
    selector: str
    picker_token: str


class TestSelectorOut(_ApiModel):
    match_count: int
    preview: dict[str, Any] = Field(default_factory=dict)


class RouteSkillCreate(_ApiModel):
    scope: str = "global"
    org_id: Optional[str] = None
    workflow_id: Optional[str] = None
    url_pattern: str
    prompt: str
    allowed_tools: Optional[list[str]] = None
    priority: int = 0
    enabled: bool = True


class RouteSkillUpdate(_ApiModel):
    prompt: Optional[str] = None
    allowed_tools: Optional[list[str]] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None


class RouteSkillOut(_ApiModel):
    id: str
    scope: str
    org_id: Optional[str] = None
    workflow_id: Optional[str] = None
    url_pattern: str
    prompt: str
    allowed_tools: list[str] = Field(default_factory=list)
    priority: int = 0
    enabled: bool = True
    created_at: datetime
    updated_at: datetime


RecordingStatus = Literal["active", "stopped", "synthesized"]


class RecordingCreate(_ApiModel):
    name: Optional[str] = None
    browser_profile_id: Optional[str] = None
    start_url: Optional[str] = None
    acquire_browser: bool = True


class RecordingEventIn(_ApiModel):
    type: str
    url: Optional[str] = None
    selector: Optional[str] = None
    element_index: Optional[int] = None
    description: Optional[str] = None
    name: Optional[str] = None
    tag: Optional[str] = None
    role: Optional[str] = None
    input_type: Optional[str] = None
    autocomplete: Optional[str] = None
    value: Optional[str] = None
    sensitive: Optional[bool] = None
    screenshot_ref: Optional[str] = None
    ts: Optional[str] = None


class RecordingEventsIn(_ApiModel):
    events: list[RecordingEventIn]


class RecordingOut(_ApiModel):
    id: str
    status: RecordingStatus
    name: Optional[str] = None
    browser_profile_id: Optional[str] = None
    start_url: Optional[str] = None
    event_count: int = 0
    events: list[dict[str, Any]] = Field(default_factory=list)
    generated_workflow_id: Optional[str] = None
    generated_workflow: Optional[dict[str, Any]] = None
    created_at: datetime
    started_at: datetime
    stopped_at: Optional[datetime] = None


class RecordingGenerateOut(_ApiModel):
    recording_id: str
    workflow_id: str
    chat_session_id: str
    workflow: dict[str, Any]
    route_skill_proposals: list["RouteSkillProposalOut"] = Field(default_factory=list)
    distill_mode: str = "rule"


RouteSkillProposalStatus = Literal["pending", "adopted", "dismissed", "superseded"]


class RouteSkillProposalOut(_ApiModel):
    id: str
    source_type: str
    source_id: str
    org_id: Optional[str] = None
    domain: str
    capability: str
    url_pattern: str
    prompt: str
    status: RouteSkillProposalStatus
    adopted_route_skill_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class RouteSkillProposalAdoptOut(_ApiModel):
    proposal: RouteSkillProposalOut
    route_skill: RouteSkillOut


class RecordingDistillIn(_ApiModel):
    use_llm: bool = False


class RecordingDistillOut(_ApiModel):
    recording_id: str
    distill_mode: str
    segments: list[dict[str, Any]] = Field(default_factory=list)
    workflow: dict[str, Any]
    route_skill_proposals: list[RouteSkillProposalOut] = Field(default_factory=list)


class TaskDistillOut(_ApiModel):
    run_id: str
    distill_mode: str
    segments: list[dict[str, Any]] = Field(default_factory=list)
    workflow: dict[str, Any]
    route_skill_proposals: list[RouteSkillProposalOut] = Field(default_factory=list)


class RouteSkillProposalAdoptPreviewOut(_ApiModel):
    proposal: RouteSkillProposalOut
    existing_route_skill: Optional[RouteSkillOut] = None
    merged_prompt: str
    will_create_new: bool


class RouteSkillBucketOut(_ApiModel):
    domain: str
    url_pattern: str
    capability: str
    route_skill_id: Optional[str] = None
    enabled: bool = False
    pending_proposals: int = 0
    prompt_preview: str = ""


class RunCreate(_ApiModel):
    browser_profile_id: Optional[str] = None
    browser_session_id: Optional[str] = None
    parameters: Optional[dict[str, Any]] = None
    totp_identifier: Optional[str] = None
    record_video: Optional[bool] = None
    execution_mode: Literal["cloud", "worker"] = "cloud"
    worker_id: Optional[str] = None
    worker_pool: Optional[str] = None


class StagingFileOut(_ApiModel):
    file_id: str
    filename: str
    content_type: str
    bytes: int


class PendingApproval(_ApiModel):
    node_id: str
    prompt: str
    inputs_schema: list[dict[str, Any]] = Field(default_factory=list)
    requested_at: datetime


class ApprovalDecisionRequest(_ApiModel):
    decision: Literal["approve", "reject"]
    inputs: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecisionResponse(_ApiModel):
    node_id: str
    decision: Literal["approve", "reject"]
    inputs: dict[str, Any] = Field(default_factory=dict)
    resolved_at: datetime


class PendingApprovalOut(_ApiModel):
    id: str
    run_id: str
    node_id: str
    seq: int
    prompt: str
    inputs_schema: list[dict[str, Any]] = Field(default_factory=list)
    requested_at: datetime


class ModelPriceEntry(_ApiModel):
    input_per_1k: float = Field(ge=0)
    output_per_1k: float = Field(ge=0)


class ModelPricesOut(_ApiModel):
    prices: dict[str, ModelPriceEntry]


class ModelPricesUpdate(_ApiModel):
    prices: dict[str, ModelPriceEntry]


class NodeCostEntry(_ApiModel):
    node_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0
    vision_calls: int = 0
    models: dict[str, Any] = Field(default_factory=dict)
    child_run_id: Optional[str] = None
    child_nodes: Optional[dict[str, Any]] = None


class UsageSummaryOut(_ApiModel):
    models: dict[str, Any] = Field(default_factory=dict)
    processed_call_ids: list[str] = Field(default_factory=list)


class RunOut(_ApiModel):
    id: str
    workflow_id: str
    workflow_version_id: str
    status: RunStatus
    mode: Literal["graph", "autonomous"] = "graph"
    queued_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    error: Optional[str]
    source: str = "manual"
    trigger_id: Optional[str] = None
    trigger_context: Optional[dict[str, Any]] = None
    parameters: Optional[dict[str, Any]] = None
    artifact_counts: dict[str, int] = Field(default_factory=dict)
    browser_profile_id: Optional[str] = None
    browser_session_id: Optional[str] = None
    browser_provider_id: Optional[str] = None
    browser_provider_metadata: dict[str, Any] = Field(default_factory=dict)
    agent_loop_metrics: Optional[dict[str, Any]] = None
    totp_identifier: Optional[str] = None
    pending_approval: Optional[PendingApproval] = None
    queue_position: Optional[int] = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_llm_calls: int = 0
    total_vision_calls: int = 0
    estimated_cost_usd: Optional[float] = None
    cost_note: Optional[str] = None
    usage_summary: Optional[UsageSummaryOut] = None
    node_costs: list[NodeCostEntry] = Field(default_factory=list)
    execution_mode: Literal["cloud", "worker"] = "cloud"
    worker_id: Optional[str] = None
    worker_pool: Optional[str] = None
    worker_name: Optional[str] = None
    queue_reason: Optional[str] = None
    objective: Optional[str] = None
    task_result: Optional["TaskResultOut"] = None


class RunArtifactOut(_ApiModel):
    id: str
    run_id: str
    kind: Literal["screenshot", "recording", "trace", "llm_trace", "download", "har"]
    content_type: str
    bytes: int
    node_id: Optional[str] = None
    step_index: Optional[int] = None
    filename: Optional[str] = None
    note: Optional[str] = None
    deleted_at: Optional[datetime] = None
    created_at: datetime
    expired: bool = False


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
    mode: Literal["graph", "autonomous"] = "graph"
    objective: Optional[str] = None
    queued_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    duration_ms: Optional[int]
    error_summary: Optional[str]
    pending_approval: Optional[PendingApproval] = None
    queue_position: Optional[int] = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_llm_calls: int = 0
    total_vision_calls: int = 0
    estimated_cost_usd: Optional[float] = None
    cost_note: Optional[str] = None
    execution_mode: Literal["cloud", "worker"] = "cloud"
    worker_id: Optional[str] = None
    worker_name: Optional[str] = None
    queue_reason: Optional[str] = None


class WorkerEnvironmentCheckOut(_ApiModel):
    id: str
    status: Literal["pass", "warn", "fail"]
    message: Optional[str] = None


class WorkerLoginRequest(_ApiModel):
    email: Optional[str] = Field(default=None, min_length=3)
    password: Optional[str] = Field(default=None, min_length=1)
    session_token: Optional[str] = Field(default=None, min_length=8)
    machine_id: str = Field(min_length=8)
    display_name: Optional[str] = None
    hostname: Optional[str] = None
    tags: list[str] = Field(default_factory=lambda: ["default"])
    agent_version: Optional[str] = None
    environment: Optional[dict[str, Any]] = None


class WorkerOAuthLoginRequest(_ApiModel):
    session_token: Optional[str] = Field(default=None, min_length=8)
    oauth_exchange_code: Optional[str] = Field(default=None, min_length=8)
    machine_id: str = Field(min_length=8)
    display_name: Optional[str] = None
    hostname: Optional[str] = None
    tags: list[str] = Field(default_factory=lambda: ["default"])
    agent_version: Optional[str] = None
    environment: Optional[dict[str, Any]] = None


class WorkerLoginResponse(_ApiModel):
    worker_session_token: str
    worker_id: str
    org_id: str
    expires_at: datetime
    approval_status: Literal["pending", "approved", "rejected"] = "pending"
    desktop_client_policy: Literal["disabled", "approval_required", "open"] = (
        "approval_required"
    )


class WorkerOut(_ApiModel):
    id: str
    machine_id: str
    display_name: Optional[str] = None
    hostname: str
    user_id: str
    user_email: Optional[str] = None
    org_id: str
    status: Literal["online", "offline"]
    tags: list[str] = Field(default_factory=list)
    max_concurrent_runs: int = 1
    active_runs: int = 0
    agent_version: Optional[str] = None
    environment_status: Literal["ready", "degraded", "not_ready", "unknown"] = "unknown"
    environment_checks: list[WorkerEnvironmentCheckOut] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    last_seen_at: Optional[datetime] = None
    created_at: datetime
    revoked_at: Optional[datetime] = None
    approval_status: Literal["pending", "approved", "rejected"] = "pending"
    approved_at: Optional[datetime] = None
    approved_by_user_id: Optional[str] = None
    desktop_client_policy: Optional[
        Literal["disabled", "approval_required", "open"]
    ] = None


class OrgSettingsOut(_ApiModel):
    org_id: str
    desktop_client_policy: Literal["disabled", "approval_required", "open"] = (
        "approval_required"
    )


class RuntimeSettingsOut(_ApiModel):
    execution_backend: str
    worker_only: bool


class OrgSettingsUpdate(_ApiModel):
    desktop_client_policy: Literal["disabled", "approval_required", "open"]


class RunCostSummaryOut(_ApiModel):
    from_: datetime = Field(alias="from")
    to: datetime
    total_runs: int
    total_input_tokens: int
    total_output_tokens: int
    total_llm_calls: int
    total_vision_calls: int
    estimated_cost_usd: Optional[float] = None
    runs_with_known_cost: int = 0
    runs_with_unknown_cost: int = 0


class RunReplayResponse(_ApiModel):
    run: RunOut
    workflow_version: WorkflowVersionOut
    events: list[RunEventOut]


class CredentialCreate(_ApiModel):
    name: str
    description: Optional[str] = None
    type: str = "generic"
    fields: dict[str, str]


class CredentialUpdate(_ApiModel):
    name: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    fields: Optional[dict[str, str]] = None


class CredentialFieldMasked(_ApiModel):
    name: str
    masked_value: str


class CredentialOut(_ApiModel):
    id: str
    name: str
    type: str = "generic"
    description: Optional[str]
    fields: list[CredentialFieldMasked]
    created_at: datetime
    updated_at: datetime


class CredentialListItem(_ApiModel):
    id: str
    name: str
    type: str = "generic"
    description: Optional[str]
    field_names: list[str]
    updated_at: datetime
    usage_count: int = 0


class CredentialTypeFieldOut(_ApiModel):
    name: str
    label: str
    kind: str
    required: bool = False
    default: Any = None


class CredentialTypeAuthOut(_ApiModel):
    strategy: str
    connect_app: Optional[str] = None


class CredentialTypeOut(_ApiModel):
    type: str
    label: str
    fields: list[CredentialTypeFieldOut]
    auth: CredentialTypeAuthOut


class WorkflowCredentialLinkRequest(_ApiModel):
    credential_id: str


class LlmConfigUpsert(_ApiModel):
    provider: str
    model: str = Field(min_length=1)
    api_key: str
    base_url: Optional[str] = None
    self_healing_enabled: Optional[bool] = None
    self_healing_vision_threshold: Optional[float] = Field(
        default=None, ge=0.0, le=1.0
    )
    selector_cache_enabled: Optional[bool] = None

    @field_validator("model")
    @classmethod
    def model_must_not_be_email(cls, value: str) -> str:
        trimmed = value.strip()
        if "@" in trimmed and "." in trimmed.split("@", 1)[-1]:
            raise ValueError("model must be a model id, not an email address")
        return trimmed


class LlmConfigOut(_ApiModel):
    id: str
    provider: str
    model: str
    api_key_masked: str
    base_url: Optional[str]
    is_active: bool
    self_healing_enabled: bool
    self_healing_vision_threshold: float
    selector_cache_enabled: bool
    created_at: datetime
    updated_at: datetime


class SelectorCacheEntryOut(_ApiModel):
    id: str
    node_id: str
    url_pattern: str
    selector: str
    kind: str
    confidence: float
    hit_count: int
    miss_count: int
    consecutive_misses: int
    last_success_at: str


class SelectorCacheStatsOut(_ApiModel):
    workflow_id: str
    entry_count: int
    total_hits: int
    total_misses: int
    entries: list[SelectorCacheEntryOut]


class LlmEffectiveOut(_ApiModel):
    source: Literal["db", "env", "none"]
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key_masked: str = ""
    base_url: Optional[str] = None


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


class NodeRetryPayload(_ApiModel):
    attempt: int
    error: str
    error_kind: str
    next_attempt_at: datetime


class RunCompletedWithErrorsPayload(_ApiModel):
    failed_node_count: int
    failed_node_ids: list[str]


class ApiKeyCreate(_ApiModel):
    name: str = Field(min_length=1, max_length=128)


class ApiKeyOut(_ApiModel):
    id: str
    name: str
    prefix: str
    created_at: datetime
    last_used_at: Optional[datetime] = None


class ApiKeyCreated(_ApiModel):
    id: str
    name: str
    prefix: str
    key: str
    created_at: datetime


class RunTaskRequest(_ApiModel):
    prompt: str = Field(min_length=1)
    url: Optional[str] = None
    data_schema: Optional[dict[str, Any]] = None
    browser_session_id: Optional[str] = None
    browser_profile_id: Optional[str] = None
    totp_identifier: Optional[str] = None
    max_steps: int = Field(default=8, ge=1, le=200)
    persist: bool = True


class RunTaskResponse(_ApiModel):
    run_id: str
    status: RunStatus


class RunListPage(_ApiModel):
    items: list[RunListItem]
    next_cursor: Optional[str] = None


class TaskCreate(_ApiModel):
    objective: str
    start_url: Optional[str] = None
    max_steps: int = Field(default=30, ge=1, le=200)
    max_seconds: int = Field(default=300, ge=1, le=3600)
    success_criteria: Optional[str] = None
    allowed_domains: Optional[list[str]] = None
    data_schema: Optional[dict[str, Any]] = None
    require_confirmation: bool = False
    allowed_tools: Optional[list[str]] = None
    synthesize_workflow: bool = False
    execution_mode: Optional[Literal["cloud", "worker"]] = None


class TaskResultOut(_ApiModel):
    success: bool
    summary: str = ""
    user_message: Optional[str] = None
    data: Optional[Any] = None
    items: list[Any] = Field(default_factory=list)
    reason: Optional[str] = None
    steps_taken: int = 0
    synthesized_workflow_id: Optional[str] = None


class TaskOut(_ApiModel):
    id: str
    mode: Literal["autonomous"] = "autonomous"
    status: RunStatus
    objective: str
    start_url: Optional[str] = None
    max_steps: int
    max_seconds: int
    success_criteria: Optional[str] = None
    allowed_domains: Optional[list[str]] = None
    data_schema: Optional[dict[str, Any]] = None
    require_confirmation: bool = False
    allowed_tools: Optional[list[str]] = None
    queued_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    result: Optional[TaskResultOut] = None


class WSEvent(_ApiModel):
    event: str
    run_id: Optional[str] = None
    node_id: Optional[str] = None
    seq: Optional[int] = None
    ts: str
    message: Optional[str] = None
    output: Optional[Any] = None
    error: Optional[str] = None
    attempt: Optional[int] = None
    error_kind: Optional[str] = None
    next_attempt_at: Optional[datetime] = None
    failed_node_count: Optional[int] = None
    failed_node_ids: Optional[list[str]] = None


__all__ = [
    "WorkflowCreate",
    "WorkflowUpdate",
    "WorkflowOut",
    "WorkflowVersionCreate",
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
    "ViewportSpec",
    "BrowserProfileCreate",
    "BrowserProfileUpdate",
    "BrowserProfileOut",
    "BrowserSessionCreate",
    "BrowserSessionOut",
    "BrowserSessionStatus",
    "RecordingCreate",
    "RecordingEventIn",
    "RecordingEventsIn",
    "RecordingOut",
    "RecordingGenerateOut",
    "RecordingStatus",
    "RunCreate",
    "StagingFileOut",
    "RunOut",
    "RunArtifactOut",
    "RunEventOut",
    "RunListItem",
    "RunReplayResponse",
    "WorkerEnvironmentCheckOut",
    "WorkerLoginRequest",
    "WorkerOAuthLoginRequest",
    "WorkerLoginResponse",
    "WorkerOut",
    "RuntimeSettingsOut",
    "RunStatus",
    "CredentialCreate",
    "CredentialUpdate",
    "CredentialOut",
    "CredentialListItem",
    "CredentialFieldMasked",
    "CredentialTypeOut",
    "CredentialTypeFieldOut",
    "CredentialTypeAuthOut",
    "WorkflowCredentialLinkRequest",
    "LlmConfigUpsert",
    "LlmConfigOut",
    "LlmEffectiveOut",
    "WSStartFrame",
    "WSAbortFrame",
    "WSClientFrame",
    "WSEvent",
    "NodeRetryPayload",
    "RunCompletedWithErrorsPayload",
    "TaskCreate",
    "TaskOut",
    "TaskResultOut",
]


# === triggers-and-scheduling additions ===

TriggerType = Literal["cron", "webhook", "manual", "poll", "app"]
TriggerAuthMode = Literal["query_secret", "hmac"]
MisfirePolicy = Literal["skip", "catch_up"]
PollMode = Literal["per_record", "batched"]
OnFirstPoll = Literal["fire_all", "fire_none", "fire_latest"]


class TriggerCreate(_ApiModel):
    type: TriggerType
    schedule_or_path: Optional[str] = None
    enabled: bool = True
    timezone: str = "Asia/Shanghai"
    misfire_policy: MisfirePolicy = "skip"
    auth_mode: TriggerAuthMode = "query_secret"
    parameters: Optional[dict[str, Any]] = None
    poll_app: Optional[str] = None
    poll_resource: Optional[str] = None
    poll_operation: Optional[str] = None
    poll_credential: Optional[str] = None
    poll_dedup_path: Optional[str] = None
    poll_mode: PollMode = "per_record"
    on_first_poll: OnFirstPoll = "fire_none"
    min_poll_interval_s: int = 60
    app_name: Optional[str] = None
    app_trigger: Optional[str] = None
    app_credential: Optional[str] = None


class TriggerUpdate(_ApiModel):
    enabled: Optional[bool] = None
    schedule_or_path: Optional[str] = None
    timezone: Optional[str] = None
    misfire_policy: Optional[MisfirePolicy] = None
    auth_mode: Optional[TriggerAuthMode] = None
    regenerate_secret: bool = False
    parameters: Optional[dict[str, Any]] = None
    poll_dedup_path: Optional[str] = None
    poll_mode: Optional[PollMode] = None
    on_first_poll: Optional[OnFirstPoll] = None
    min_poll_interval_s: Optional[int] = None


class TriggerOut(_ApiModel):
    id: str
    workflow_id: str
    type: TriggerType
    schedule_or_path: str
    enabled: bool
    timezone: str = "Asia/Shanghai"
    misfire_policy: MisfirePolicy = "skip"
    next_run_at: Optional[datetime] = None
    auth_mode: TriggerAuthMode
    last_fired_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    webhook_url: Optional[str] = None
    secret_masked: Optional[str] = None
    secret_full: Optional[str] = None
    poll_app: Optional[str] = None
    poll_resource: Optional[str] = None
    poll_operation: Optional[str] = None
    poll_credential: Optional[str] = None
    poll_dedup_path: Optional[str] = None
    poll_mode: PollMode = "per_record"
    on_first_poll: OnFirstPoll = "fire_none"
    min_poll_interval_s: int = 60
    last_polled_at: Optional[datetime] = None
    app_name: Optional[str] = None
    app_trigger: Optional[str] = None
    app_credential: Optional[str] = None
    subscription_id: Optional[str] = None
    app_callback_url: Optional[str] = None
    subscription_status: Optional[str] = None
    parameters: Optional[dict[str, Any]] = None


class AppTriggerFireResponse(_ApiModel):
    run_id: Optional[str] = None
    status: Literal["queued", "challenge", "duplicate"] = "queued"
    challenge: Optional[str] = None


class WebhookFireResponse(_ApiModel):
    run_id: str
    status: Literal["queued"] = "queued"


class NextFiresResponse(_ApiModel):
    trigger_id: str
    timezone: str
    fires: list[datetime] = Field(default_factory=list)


class LastOutputShapesResponse(_ApiModel):
    run_id: Optional[str] = None
    started_at: Optional[datetime] = None
    shapes: dict[str, Any] = Field(default_factory=dict)


# === outbound-webhooks-hmac additions ===

WebhookEventName = Literal[
    "run_completed",
    "run_failed",
    "run_rejected",
    "run_aborted",
    "approval_requested",
]
WebhookDeliveryStatus = Literal["pending", "delivered", "failed", "exhausted"]


class WebhookSubscriptionCreate(_ApiModel):
    url: str
    events: list[WebhookEventName]
    secret: Optional[str] = None
    enabled: bool = True
    workflow_id: Optional[str] = None


class WebhookSubscriptionUpdate(_ApiModel):
    url: Optional[str] = None
    events: Optional[list[WebhookEventName]] = None
    secret: Optional[str] = None
    enabled: Optional[bool] = None
    workflow_id: Optional[str] = None


class WebhookSubscriptionOut(_ApiModel):
    id: str
    url: str
    events: list[WebhookEventName]
    enabled: bool
    workflow_id: Optional[str]
    secret_masked: str
    created_at: datetime
    updated_at: datetime


class WebhookDeliveryOut(_ApiModel):
    id: str
    subscription_id: str
    event: str
    attempt: int
    status: WebhookDeliveryStatus
    response_code: Optional[int]
    next_attempt_at: Optional[datetime]
    signature: Optional[str]
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class WebhookTestResponse(_ApiModel):
    delivery_id: str
    status: Literal["queued"] = "queued"


class WebhookReplayResponse(_ApiModel):
    delivery_id: str
    status: Literal["pending"] = "pending"


class AntibotSettingsOut(_ApiModel):
    source: Literal["env"] = "env"
    editable: bool = False
    captcha_detection_enabled: bool
    captcha_builtin_heuristics_enabled: bool
    captcha_solver: Literal["manual", "external"]
    captcha_external_solver_url_masked: Optional[str] = None
    captcha_external_solver_key_configured: bool = False
    antibot_stealth: bool
    antibot_user_agent: Optional[str] = None
    antibot_locale: Optional[str] = None
    antibot_timezone_id: Optional[str] = None
    antibot_viewport_width: Optional[int] = None
    antibot_viewport_height: Optional[int] = None
    default_proxy_id: Optional[str] = None
    proxy_configured: bool = False
    proxy_url_masked: Optional[str] = None
    proxy_username_configured: bool = False
    proxy_password_configured: bool = False


class ExpressionPreviewRequest(_ApiModel):
    expression: str
    workflow_id: Optional[str] = None
    context: dict[str, Any] = Field(default_factory=dict)


class ExpressionPreviewResponse(_ApiModel):
    ok: bool
    type: Optional[str] = None
    value: Any = None
    error: Optional[str] = None


__all__ += [
    "TriggerType",
    "TriggerAuthMode",
    "MisfirePolicy",
    "PollMode",
    "OnFirstPoll",
    "TriggerCreate",
    "TriggerUpdate",
    "TriggerOut",
    "WebhookFireResponse",
    "NextFiresResponse",
    "AppTriggerFireResponse",
    "LastOutputShapesResponse",
    "WebhookEventName",
    "WebhookDeliveryStatus",
    "WebhookSubscriptionCreate",
    "WebhookSubscriptionUpdate",
    "WebhookSubscriptionOut",
    "WebhookDeliveryOut",
    "WebhookTestResponse",
    "WebhookReplayResponse",
    "ApiKeyCreate",
    "ApiKeyOut",
    "ApiKeyCreated",
    "RunTaskRequest",
    "RunTaskResponse",
    "RunListPage",
    "AntibotSettingsOut",
    "ExpressionPreviewRequest",
    "ExpressionPreviewResponse",
]
