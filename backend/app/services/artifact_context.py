"""Per-run context for artifact capture (run_id, optional node/step)."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional


_run_id: ContextVar[Optional[str]] = ContextVar("artifact_run_id", default=None)
_node_id: ContextVar[Optional[str]] = ContextVar("artifact_node_id", default=None)
_step_index: ContextVar[Optional[int]] = ContextVar("artifact_step_index", default=None)
_sensitive: ContextVar[list[tuple[str, str, str]]] = ContextVar(
    "artifact_sensitive_values",
    default=[],
)


def set_run_context(
    run_id: Optional[str],
    *,
    node_id: Optional[str] = None,
    step_index: Optional[int] = None,
) -> None:
    _run_id.set(run_id)
    _node_id.set(node_id)
    _step_index.set(step_index)


def get_run_id() -> Optional[str]:
    return _run_id.get()


def get_node_id() -> Optional[str]:
    return _node_id.get()


def get_step_index() -> Optional[int]:
    return _step_index.get()


def register_sensitive(
    field_name: str,
    value: str,
    *,
    credential_type: str = "generic",
) -> None:
    """Track a plaintext secret for LLM trace masking within the current run."""
    if not value:
        return
    current = list(_sensitive.get())
    if any(existing == value for _, existing, _ in current):
        return
    current.append((field_name, value, credential_type))
    _sensitive.set(current)


def get_sensitive_values() -> list[tuple[str, str, str]]:
    return list(_sensitive.get())


def clear_run_context() -> None:
    set_run_context(None)
    _sensitive.set([])


__all__ = [
    "clear_run_context",
    "get_node_id",
    "get_run_id",
    "get_sensitive_values",
    "get_step_index",
    "register_sensitive",
    "set_run_context",
]
