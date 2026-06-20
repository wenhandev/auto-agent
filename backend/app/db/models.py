from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import JSON, LargeBinary, UniqueConstraint, text
from sqlmodel import Column, Field, Index, SQLModel


def _uuid() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Workflow(SQLModel, table=True):
    __tablename__ = "workflow"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = None
    status: str = Field(default="active", index=True, nullable=False)
    org_id: Optional[str] = Field(default=None, foreign_key="organization.id", index=True)
    created_by: Optional[str] = Field(default=None, foreign_key="user.id", index=True)
    visibility: str = Field(default="org", index=True, nullable=False)
    current_version_id: Optional[str] = Field(
        default=None, foreign_key="workflow_version.id"
    )
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)


class WorkflowVersion(SQLModel, table=True):
    __tablename__ = "workflow_version"

    id: str = Field(default_factory=_uuid, primary_key=True)
    workflow_id: str = Field(foreign_key="workflow.id", index=True)
    version_index: int = Field(nullable=False)
    nodes_json: str = Field(nullable=False)
    edges_json: str = Field(nullable=False)
    start_id: str = Field(nullable=False)
    parameters_json: str = Field(default="[]", nullable=False)
    authored_by: str = Field(nullable=False)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_workflow_version_workflow_version", "workflow_id", "version_index"),
    )


class ChatSession(SQLModel, table=True):
    __tablename__ = "chat_session"

    id: str = Field(default_factory=_uuid, primary_key=True)
    workflow_id: str = Field(foreign_key="workflow.id", index=True)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_message"

    id: str = Field(default_factory=_uuid, primary_key=True)
    session_id: str = Field(foreign_key="chat_session.id", index=True)
    role: str = Field(nullable=False)
    content: str = Field(nullable=False)
    workflow_version_id: Optional[str] = Field(
        default=None, foreign_key="workflow_version.id"
    )
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


class Run(SQLModel, table=True):
    __tablename__ = "run"

    id: str = Field(default_factory=_uuid, primary_key=True)
    org_id: Optional[str] = Field(default=None, foreign_key="organization.id", index=True)
    workflow_id: str = Field(foreign_key="workflow.id", index=True)
    workflow_version_id: str = Field(foreign_key="workflow_version.id")
    status: str = Field(default="queued", index=True, nullable=False)
    mode: str = Field(default="graph", index=True, nullable=False)
    queued_at: datetime = Field(default_factory=_utcnow, nullable=False)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    source: str = Field(default="manual", nullable=False)
    trigger_id: Optional[str] = Field(default=None, foreign_key="trigger.id")
    trigger_context_json: Optional[str] = Field(default=None)
    parameters_json: Optional[str] = Field(default=None)
    parent_run_id: Optional[str] = Field(default=None, foreign_key="run.id", index=True)
    # autonomous task fields (null for graph runs)
    objective: Optional[str] = None
    start_url: Optional[str] = None
    max_steps: Optional[int] = None
    max_seconds: Optional[int] = None
    success_criteria: Optional[str] = None
    allowed_domains_json: Optional[str] = None
    data_schema_json: Optional[str] = None
    require_confirmation: bool = Field(default=False, nullable=False)
    allowed_tools_json: Optional[str] = None
    result_json: Optional[str] = None
    browser_profile_id: Optional[str] = Field(
        default=None, foreign_key="browser_profile.id", index=True
    )
    browser_session_id: Optional[str] = Field(
        default=None, foreign_key="browser_session.id", index=True
    )
    proxy_id: Optional[str] = Field(
        default=None, foreign_key="proxy_config.id", index=True
    )
    totp_identifier: Optional[str] = None
    record_video: Optional[bool] = Field(default=None)
    total_input_tokens: int = Field(default=0, nullable=False)
    total_output_tokens: int = Field(default=0, nullable=False)
    total_llm_calls: int = Field(default=0, nullable=False)
    total_vision_calls: int = Field(default=0, nullable=False)
    estimated_cost_usd: Optional[float] = None
    cost_note: Optional[str] = None
    usage_summary_json: Optional[str] = None
    node_cost_json: Optional[str] = None
    browser_provider_id: Optional[str] = Field(default=None, index=True)
    browser_provider_metadata_json: Optional[str] = None
    agent_loop_metrics_json: Optional[str] = None
    execution_mode: str = Field(default="cloud", index=True, nullable=False)
    worker_id: Optional[str] = Field(default=None, foreign_key="worker.id", index=True)
    worker_pool: Optional[str] = Field(default=None, index=True)
    worker_assigned_at: Optional[datetime] = None


class RunEvent(SQLModel, table=True):
    __tablename__ = "run_event"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="run.id", index=True)
    seq: int = Field(nullable=False)
    event_type: str = Field(nullable=False)
    node_id: Optional[str] = None
    ts: datetime = Field(default_factory=_utcnow, nullable=False)
    payload_json: str = Field(nullable=False)

    __table_args__ = (
        Index("ix_run_event_run_seq", "run_id", "seq"),
    )


class RunApproval(SQLModel, table=True):
    __tablename__ = "run_approval"

    id: str = Field(default_factory=_uuid, primary_key=True)
    run_id: str = Field(foreign_key="run.id", index=True)
    node_id: str
    seq: int
    prompt: str
    inputs_schema: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    decision: Optional[str] = Field(default=None)
    decision_inputs: dict = Field(default_factory=dict, sa_column=Column(JSON))
    requested_at: datetime = Field(default_factory=_utcnow, nullable=False)
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None

    __table_args__ = (
        UniqueConstraint("run_id", "seq", name="uq_run_approval_run_seq"),
        Index("ix_run_approval_run_pending", "run_id", "decision"),
    )


class RunArtifact(SQLModel, table=True):
    __tablename__ = "run_artifact"

    id: str = Field(default_factory=_uuid, primary_key=True)
    run_id: str = Field(foreign_key="run.id", index=True)
    kind: str = Field(index=True, nullable=False)
    path: str = Field(nullable=False)
    content_type: str = Field(nullable=False)
    bytes: int = Field(default=0, nullable=False)
    node_id: Optional[str] = None
    step_index: Optional[int] = None
    content_hash: Optional[str] = Field(default=None, index=True)
    filename: Optional[str] = None
    note: Optional[str] = None
    deleted_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)

    __table_args__ = (
        Index("ix_run_artifact_run_kind", "run_id", "kind"),
    )


class Credential(SQLModel, table=True):
    __tablename__ = "credential"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(index=True, unique=True, nullable=False)
    org_id: Optional[str] = Field(default=None, foreign_key="organization.id", index=True)
    created_by: Optional[str] = Field(default=None, foreign_key="user.id", index=True)
    type: str = Field(default="generic", nullable=False)
    description: Optional[str] = None
    ciphertext: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)


class WorkflowCredential(SQLModel, table=True):
    __tablename__ = "workflow_credential"

    id: Optional[int] = Field(default=None, primary_key=True)
    workflow_id: str = Field(foreign_key="workflow.id", index=True, nullable=False)
    credential_id: str = Field(foreign_key="credential.id", index=True, nullable=False)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "workflow_id", "credential_id", name="uq_workflow_credential_pair"
        ),
    )


class LlmConfig(SQLModel, table=True):
    __tablename__ = "llm_config"

    id: str = Field(default_factory=_uuid, primary_key=True)
    provider: str = Field(nullable=False)
    model: str = Field(nullable=False)
    api_key_ciphertext: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    base_url: Optional[str] = None
    is_active: bool = Field(default=False, nullable=False, index=True)
    self_healing_enabled: bool = Field(default=True, nullable=False)
    self_healing_vision_threshold: float = Field(
        default=0.6, ge=0.0, le=1.0, nullable=False
    )
    selector_cache_enabled: bool = Field(default=True, nullable=False)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)


class SelectorCache(SQLModel, table=True):
    __tablename__ = "selector_cache"

    id: str = Field(default_factory=_uuid, primary_key=True)
    workflow_id: str = Field(foreign_key="workflow.id", index=True, nullable=False)
    node_id: str = Field(index=True, nullable=False)
    url_pattern: str = Field(nullable=False)
    selector: str = Field(nullable=False)
    kind: str = Field(default="selector", nullable=False)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, nullable=False)
    plan_json: Optional[str] = Field(default=None)
    last_success_at: datetime = Field(default_factory=_utcnow, nullable=False)
    hit_count: int = Field(default=0, nullable=False)
    miss_count: int = Field(default=0, nullable=False)
    consecutive_misses: int = Field(default=0, nullable=False)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "workflow_id",
            "node_id",
            "url_pattern",
            name="uq_selector_cache_workflow_node_url",
        ),
        Index("ix_selector_cache_workflow", "workflow_id"),
    )


__all__ = [
    "Workflow",
    "WorkflowVersion",
    "ChatSession",
    "ChatMessage",
    "Run",
    "RunEvent",
    "RunArtifact",
    "Credential",
    "WorkflowCredential",
    "LlmConfig",
    "SelectorCache",
]


# === triggers-and-scheduling additions ===

class Trigger(SQLModel, table=True):
    __tablename__ = "trigger"

    id: str = Field(default_factory=_uuid, primary_key=True)
    workflow_id: str = Field(foreign_key="workflow.id", index=True, nullable=False)
    type: str = Field(nullable=False, index=True)
    schedule_or_path: str = Field(nullable=False)
    enabled: bool = Field(default=True, nullable=False)
    timezone: str = Field(default="Asia/Shanghai", nullable=False)
    next_run_at: Optional[datetime] = None
    misfire_policy: str = Field(default="skip", nullable=False)
    secret_ciphertext: Optional[bytes] = Field(
        default=None, sa_column=Column(LargeBinary, nullable=True)
    )
    auth_mode: str = Field(default="query_secret", nullable=False)
    last_fired_at: Optional[datetime] = None
    parameters_json: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)
    # poll trigger state
    poll_app: Optional[str] = None
    poll_resource: Optional[str] = None
    poll_operation: Optional[str] = None
    poll_credential: Optional[str] = None
    poll_dedup_path: Optional[str] = None
    poll_cursor: Optional[str] = None
    last_seen_key: Optional[str] = None
    seen_keys_json: Optional[str] = None
    poll_mode: str = Field(default="per_record", nullable=False)
    on_first_poll: str = Field(default="fire_none", nullable=False)
    min_poll_interval_s: int = Field(default=60, nullable=False)
    last_polled_at: Optional[datetime] = None
    first_poll_done: bool = Field(default=False, nullable=False)
    # app trigger state
    app_name: Optional[str] = None
    app_trigger: Optional[str] = None
    app_credential: Optional[str] = None
    subscription_id: Optional[str] = None
    subscription_secret_ciphertext: Optional[bytes] = Field(
        default=None, sa_column=Column(LargeBinary, nullable=True)
    )

    __table_args__ = (
        Index(
            "uq_trigger_webhook_path",
            "schedule_or_path",
            unique=True,
            sqlite_where=text("type='webhook'"),
        ),
    )


class ProcessedEvent(SQLModel, table=True):
    """Bounded idempotency store for app webhook deliveries."""

    __tablename__ = "processed_event"

    id: Optional[int] = Field(default=None, primary_key=True)
    trigger_id: str = Field(foreign_key="trigger.id", index=True, nullable=False)
    event_id: str = Field(nullable=False, index=True)
    processed_at: datetime = Field(default_factory=_utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("trigger_id", "event_id", name="uq_processed_event_pair"),
    )


__all__ += ["Trigger", "ProcessedEvent"]


# === browser-sessions-profiles additions ===


# === captcha-antibot-proxy: proxy table (before profile FK) ===


class ProxyConfig(SQLModel, table=True):
    __tablename__ = "proxy_config"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(index=True, unique=True, nullable=False)
    server: str = Field(nullable=False)
    username: Optional[str] = None
    password_ciphertext: Optional[bytes] = Field(
        default=None, sa_column=Column(LargeBinary, nullable=True)
    )
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)


class BrowserProfile(SQLModel, table=True):
    __tablename__ = "browser_profile"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(index=True, unique=True, nullable=False)
    storage_state_path: Optional[str] = None
    user_agent: Optional[str] = None
    viewport_json: Optional[str] = None
    locale: Optional[str] = None
    timezone_id: Optional[str] = None
    proxy_id: Optional[str] = Field(default=None, foreign_key="proxy_config.id", index=True)
    persist_cookies: bool = Field(default=True, nullable=False)
    persist_local_storage: bool = Field(default=True, nullable=False)
    owner_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)
    last_used_at: Optional[datetime] = None


class BrowserSession(SQLModel, table=True):
    __tablename__ = "browser_session"

    id: str = Field(default_factory=_uuid, primary_key=True)
    profile_id: Optional[str] = Field(
        default=None, foreign_key="browser_profile.id", index=True
    )
    status: str = Field(default="live", index=True, nullable=False)
    started_at: datetime = Field(default_factory=_utcnow, nullable=False)
    expires_at: datetime = Field(nullable=False)
    last_activity_at: datetime = Field(default_factory=_utcnow, nullable=False)
    memory_json: Optional[str] = Field(default=None)
    provider_id: str = Field(default="local_playwright", index=True, nullable=False)
    provider_metadata_json: Optional[str] = Field(default=None)


class RouteSkill(SQLModel, table=True):
    __tablename__ = "route_skill"

    id: str = Field(default_factory=_uuid, primary_key=True)
    scope: str = Field(default="global", index=True, nullable=False)
    org_id: Optional[str] = Field(default=None, foreign_key="organization.id", index=True)
    workflow_id: Optional[str] = Field(default=None, foreign_key="workflow.id", index=True)
    url_pattern: str = Field(index=True, nullable=False)
    prompt: str = Field(nullable=False)
    allowed_tools_json: Optional[str] = None
    priority: int = Field(default=0, index=True, nullable=False)
    enabled: bool = Field(default=True, index=True, nullable=False)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)


__all__ += ["BrowserProfile", "BrowserSession", "ProxyConfig", "RouteSkill"]


# === outbound-webhooks-hmac additions ===


class WebhookSubscription(SQLModel, table=True):
    __tablename__ = "webhook_subscription"

    id: str = Field(default_factory=_uuid, primary_key=True)
    url: str = Field(nullable=False)
    events: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    secret_ciphertext: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    enabled: bool = Field(default=True, nullable=False, index=True)
    workflow_id: Optional[str] = Field(
        default=None, foreign_key="workflow.id", index=True
    )
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)


class WebhookDelivery(SQLModel, table=True):
    __tablename__ = "webhook_delivery"

    id: str = Field(default_factory=_uuid, primary_key=True)
    subscription_id: str = Field(
        foreign_key="webhook_subscription.id", index=True, nullable=False
    )
    event: str = Field(nullable=False, index=True)
    payload_json: str = Field(nullable=False)
    attempt: int = Field(default=0, nullable=False)
    status: str = Field(default="pending", index=True, nullable=False)
    response_code: Optional[int] = None
    next_attempt_at: Optional[datetime] = Field(default=None, index=True)
    signature: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)


__all__ += ["WebhookSubscription", "WebhookDelivery"]


# === public-api-and-auth additions ===


class ApiKey(SQLModel, table=True):
    __tablename__ = "api_key"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(index=True, nullable=False)
    key_hash: str = Field(index=True, unique=True, nullable=False)
    prefix: str = Field(nullable=False)
    org_id: Optional[str] = Field(default=None, foreign_key="organization.id", index=True)
    owner_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    last_used_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = Field(default=None, index=True)


__all__ += ["ApiKey"]


# === multi-user-orgs ===


class Organization(SQLModel, table=True):
    __tablename__ = "organization"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(index=True, nullable=False)
    desktop_client_policy: str = Field(
        default="approval_required", nullable=False
    )
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


class User(SQLModel, table=True):
    __tablename__ = "user"

    id: str = Field(default_factory=_uuid, primary_key=True)
    email: str = Field(index=True, unique=True, nullable=False)
    password_hash: Optional[str] = None
    name: Optional[str] = None
    idp_subject: Optional[str] = Field(default=None, index=True)
    is_platform_admin: bool = Field(default=False, nullable=False)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    disabled_at: Optional[datetime] = None


class UserIdentity(SQLModel, table=True):
    __tablename__ = "user_identity"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True, nullable=False)
    provider: str = Field(index=True, nullable=False)
    provider_subject_id: str = Field(index=True, nullable=False)
    email_at_link: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_subject_id",
            name="uq_user_identity_provider_subject",
        ),
    )


class OrgMembership(SQLModel, table=True):
    __tablename__ = "org_membership"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True, nullable=False)
    org_id: str = Field(foreign_key="organization.id", index=True, nullable=False)
    role: str = Field(default="member", nullable=False)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "org_id", name="uq_org_membership_user_org"),
    )


class OAuthDomainRule(SQLModel, table=True):
    __tablename__ = "oauth_domain_rule"

    id: str = Field(default_factory=_uuid, primary_key=True)
    domain: str = Field(index=True, unique=True, nullable=False)
    org_id: str = Field(foreign_key="organization.id", index=True, nullable=False)
    default_role: str = Field(default="member", nullable=False)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)


__all__ += [
    "Organization",
    "User",
    "UserIdentity",
    "OrgMembership",
    "OAuthDomainRule",
]


# === local runtime worker ===


class Worker(SQLModel, table=True):
    __tablename__ = "worker"

    id: str = Field(default_factory=_uuid, primary_key=True)
    machine_id: str = Field(index=True, nullable=False)
    display_name: Optional[str] = None
    hostname: str = Field(default="unknown", nullable=False)
    org_id: str = Field(foreign_key="organization.id", index=True, nullable=False)
    user_id: str = Field(foreign_key="user.id", index=True, nullable=False)
    tags_json: str = Field(default='["default"]', nullable=False)
    max_concurrent_runs: int = Field(default=1, nullable=False)
    agent_version: Optional[str] = None
    environment_status: str = Field(default="unknown", nullable=False)
    environment_checks_json: Optional[str] = None
    capabilities_json: Optional[str] = None
    status: str = Field(default="offline", index=True, nullable=False)
    approval_status: str = Field(default="pending", nullable=False)
    approved_at: Optional[datetime] = None
    approved_by_user_id: Optional[str] = Field(default=None, foreign_key="user.id")
    last_seen_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    revoked_at: Optional[datetime] = Field(default=None, index=True)

    __table_args__ = (
        UniqueConstraint("org_id", "user_id", "machine_id", name="uq_worker_org_user_machine"),
    )


class WorkerSession(SQLModel, table=True):
    __tablename__ = "worker_session"

    id: str = Field(default_factory=_uuid, primary_key=True)
    worker_id: str = Field(foreign_key="worker.id", index=True, nullable=False)
    token_hash: str = Field(index=True, unique=True, nullable=False)
    prefix: str = Field(nullable=False)
    expires_at: datetime = Field(nullable=False)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    revoked_at: Optional[datetime] = Field(default=None, index=True)


__all__ += ["Worker", "WorkerSession"]


# === record-and-generate additions ===


class Recording(SQLModel, table=True):
    __tablename__ = "recording"

    id: str = Field(default_factory=_uuid, primary_key=True)
    status: str = Field(default="active", index=True, nullable=False)
    name: Optional[str] = None
    browser_profile_id: Optional[str] = Field(
        default=None, foreign_key="browser_profile.id", index=True
    )
    start_url: Optional[str] = None
    events_json: str = Field(default="[]", nullable=False)
    generated_workflow_id: Optional[str] = Field(
        default=None, foreign_key="workflow.id", index=True
    )
    generated_workflow_json: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    started_at: datetime = Field(default_factory=_utcnow, nullable=False)
    stopped_at: Optional[datetime] = None


__all__ += ["Recording"]
