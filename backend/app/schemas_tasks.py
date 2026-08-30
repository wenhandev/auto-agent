"""Pydantic models for autonomous task mode."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

RunMode = Literal["graph", "autonomous"]

DEFAULT_MAX_STEPS = 30
DEFAULT_MAX_SECONDS = 300

# Browser-centric default. Desktop tools are opt-in via TaskSpec.allowed_tools
# (or an explicit desktop-oriented allowlist).
DEFAULT_ALLOWED_TOOLS: list[str] = [
    "navigate",
    "click_element",
    "type_text",
    "select_option",
    "scroll",
    "drag_element",
    "go_back",
    "wait",
    "extract",
    "finish",
    "http_request",
]

DEFAULT_DESKTOP_ALLOWED_TOOLS: list[str] = [
    "list_apps",
    "open_app",
    "get_app_state",
    "desktop_click",
    "desktop_type",
    "desktop_key",
    "desktop_scroll",
    "finish",
    "wait",
]

VISION_TOOLS = frozenset({
    "navigate",
    "click_element",
    "type_text",
    "select_option",
    "scroll",
    "drag_element",
    "go_back",
    "wait",
    "extract",
    "finish",
})

DESKTOP_TOOLS = frozenset({
    "list_apps",
    "open_app",
    "get_app_state",
    "desktop_click",
    "desktop_type",
    "desktop_key",
    "desktop_scroll",
})

NODE_TOOLS = frozenset({
    "http_request",
    "integration",
    "set",
    "filter",
    "sort",
    "limit",
    "aggregate",
    "split_out",
    "remove_duplicates",
    "rename_keys",
    "datetime",
})


class TaskSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str
    start_url: Optional[str] = None
    max_steps: int = Field(default=DEFAULT_MAX_STEPS, ge=1, le=200)
    max_seconds: int = Field(default=DEFAULT_MAX_SECONDS, ge=1, le=3600)
    success_criteria: Optional[str] = None
    allowed_domains: Optional[list[str]] = None
    data_schema: Optional[dict[str, Any]] = None
    require_confirmation: bool = False
    allowed_tools: Optional[list[str]] = None
    synthesize_workflow: bool = False
    session_memory: Optional[list[dict[str, Any]]] = None


class TaskResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool
    summary: str = ""
    user_message: Optional[str] = None
    data: Optional[Any] = None
    items: list[Any] = Field(default_factory=list)
    reason: Optional[str] = None
    steps_taken: int = 0
    synthesized_workflow_id: Optional[str] = None


class PlanItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    status: Literal["pending", "in_progress", "done", "skipped"] = "pending"


__all__ = [
    "RunMode",
    "DEFAULT_MAX_STEPS",
    "DEFAULT_MAX_SECONDS",
    "DEFAULT_ALLOWED_TOOLS",
    "DEFAULT_DESKTOP_ALLOWED_TOOLS",
    "VISION_TOOLS",
    "DESKTOP_TOOLS",
    "NODE_TOOLS",
    "TaskSpec",
    "TaskResult",
    "PlanItem",
]
