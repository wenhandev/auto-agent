"""Persist masked LLM diagnostic traces as run artifacts."""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from sqlmodel import Session

from app.db.models import RunArtifact
from app.services import artifact_context
from app.services import artifacts as artifact_svc
from app.services.credential_masking import mask_field
from app.db.models import RunArtifact


def register_sensitive(
    field_name: str,
    value: str,
    *,
    credential_type: str = "generic",
) -> None:
    """Register a plaintext secret for masking in subsequent trace writes."""
    artifact_context.register_sensitive(field_name, value, credential_type=credential_type)


def _mask_string(text: str) -> str:
    if not text:
        return text
    result = text
    for field_name, value, cred_type in artifact_context.get_sensitive_values():
        if not value or len(value) < 2:
            continue
        if value not in result:
            continue
        masked = mask_field(field_name, value, credential_type=cred_type)
        result = result.replace(value, masked)
    return result


def mask_trace_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Recursively mask registered secrets in a trace payload."""

    def walk(value: Any) -> Any:
        if isinstance(value, str):
            return _mask_string(value)
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, dict):
            return {key: walk(item) for key, item in value.items()}
        return value

    return walk(payload)


def build_trace_payload(
    *,
    model: str,
    system: Optional[str] = None,
    messages: Optional[list[Any]] = None,
    response: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    latency_ms: Optional[int] = None,
    call_id: Optional[str] = None,
    vision: bool = False,
) -> dict[str, Any]:
    tokens: dict[str, Optional[int]] = {
        "input": input_tokens,
        "output": output_tokens,
    }
    payload: dict[str, Any] = {
        "call_id": call_id or uuid.uuid4().hex,
        "model": model,
        "system": system,
        "messages": messages or [],
        "response": response,
        "tokens": tokens,
        "latency_ms": latency_ms,
    }
    if vision:
        payload["vision"] = True
    return payload


def persist_llm_trace(
    run_id: str,
    payload: dict[str, Any],
    *,
    node_id: Optional[str] = None,
    step_index: Optional[int] = None,
    session: Optional[Session] = None,
) -> RunArtifact:
    """Mask secrets and store an ``llm_trace`` artifact linked to node/step."""
    masked = mask_trace_payload(payload)
    return artifact_svc.store_llm_trace_json(
        run_id,
        masked,
        node_id=node_id or artifact_context.get_node_id(),
        step_index=step_index if step_index is not None else artifact_context.get_step_index(),
        session=session,
    )


def record_llm_trace(
    *,
    model: str,
    system: Optional[str] = None,
    messages: Optional[list[Any]] = None,
    response: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    latency_ms: Optional[int] = None,
    call_id: Optional[str] = None,
    vision: bool = False,
    node_id: Optional[str] = None,
    step_index: Optional[int] = None,
    session: Optional[Session] = None,
) -> Optional[RunArtifact]:
    """Best-effort trace write when a run context is active."""
    run_id = artifact_context.get_run_id()
    if not run_id:
        return None
    payload = build_trace_payload(
        model=model,
        system=system,
        messages=messages,
        response=response,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        call_id=call_id,
        vision=vision,
    )
    return persist_llm_trace(
        run_id,
        payload,
        node_id=node_id,
        step_index=step_index,
        session=session,
    )


class LlmCallTracer:
    """Context manager to capture latency for a single LLM call."""

    def __init__(self) -> None:
        self.latency_ms: Optional[int] = None
        self._start: Optional[float] = None

    def __enter__(self) -> LlmCallTracer:
        self._start = time.monotonic()
        return self

    def __exit__(self, *_: Any) -> None:
        if self._start is not None:
            self.latency_ms = int((time.monotonic() - self._start) * 1000)


__all__ = [
    "LlmCallTracer",
    "build_trace_payload",
    "mask_trace_payload",
    "persist_llm_trace",
    "record_llm_trace",
    "register_sensitive",
]
