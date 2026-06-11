from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import LargeBinary, UniqueConstraint, text
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
    workflow_id: str = Field(foreign_key="workflow.id", index=True)
    workflow_version_id: str = Field(foreign_key="workflow_version.id")
    status: str = Field(default="queued", index=True, nullable=False)
    queued_at: datetime = Field(default_factory=_utcnow, nullable=False)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    source: str = Field(default="manual", nullable=False)
    trigger_id: Optional[str] = Field(default=None, foreign_key="trigger.id")
    trigger_context_json: Optional[str] = Field(default=None)


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


class Credential(SQLModel, table=True):
    __tablename__ = "credential"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(index=True, unique=True, nullable=False)
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
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)


__all__ = [
    "Workflow",
    "WorkflowVersion",
    "ChatSession",
    "ChatMessage",
    "Run",
    "RunEvent",
    "Credential",
    "WorkflowCredential",
    "LlmConfig",
]


# === triggers-and-scheduling additions ===

class Trigger(SQLModel, table=True):
    __tablename__ = "trigger"

    id: str = Field(default_factory=_uuid, primary_key=True)
    workflow_id: str = Field(foreign_key="workflow.id", index=True, nullable=False)
    type: str = Field(nullable=False, index=True)
    schedule_or_path: str = Field(nullable=False)
    enabled: bool = Field(default=True, nullable=False)
    secret_ciphertext: Optional[bytes] = Field(
        default=None, sa_column=Column(LargeBinary, nullable=True)
    )
    auth_mode: str = Field(default="query_secret", nullable=False)
    last_fired_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)

    __table_args__ = (
        Index(
            "uq_trigger_webhook_path",
            "schedule_or_path",
            unique=True,
            sqlite_where=text("type='webhook'"),
        ),
    )


__all__ += ["Trigger"]
