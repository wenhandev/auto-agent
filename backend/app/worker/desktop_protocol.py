"""Structured message protocol for desktop runtime IPC (Phase 4B).

Frame format: 4-byte big-endian length + UTF-8 JSON body.
"""

from __future__ import annotations

import json
import struct
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

from app.worker.desktop_api import DesktopApi, DesktopApiError


PROTOCOL_VERSION = 1
MAX_FRAME_BYTES = 16 * 1024 * 1024


class ErrorBody(BaseModel):
    code: str
    message: str
    status: int = 400


class RequestEnvelope(BaseModel):
    v: int = PROTOCOL_VERSION
    id: str = Field(min_length=1)
    method: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


class ResponseEnvelope(BaseModel):
    v: int = PROTOCOL_VERSION
    id: str
    ok: bool
    result: Any | None = None
    error: ErrorBody | None = None


Handler = Callable[[DesktopApi, dict[str, Any]], Any | Awaitable[Any]]


def _path_param(params: dict[str, Any], key: str) -> str:
    val = params.get(key)
    if not val:
        raise DesktopApiError(f"missing params.{key}", code="invalid_params", status=422)
    return str(val)


METHODS: dict[str, Handler] = {
    "health": lambda api, _p: api.health(),
    "ready": lambda api, _p: api.ready(),
    "status": lambda api, _p: api.get_status(),
    "doctor": lambda api, _p: api.run_doctor(),
    "session.save": lambda api, p: api.save_session(p),
    "session.clear": lambda api, _p: api.clear_session(),
    "settings.llm.get": lambda api, _p: api.get_llm_settings(),
    "settings.llm.put": lambda api, p: api.put_llm_settings(p),
    "settings.computer_use.get": lambda api, _p: api.get_computer_use_settings(),
    "settings.computer_use.put": lambda api, p: api.put_computer_use_settings(p),
    "cloud.workflows.list": lambda api, _p: api.list_cloud_workflows(),
    "cloud.workflows.get": lambda api, p: api.get_cloud_workflow(_path_param(p, "workflow_id")),
    "cloud.workflows.pull": lambda api, p: api.pull_cloud_workflow(_path_param(p, "workflow_id")),
    "drafts.list": lambda api, _p: api.list_drafts(),
    "drafts.get": lambda api, p: api.get_draft(_path_param(p, "local_id")),
    "drafts.save": lambda api, p: api.save_draft(p),
    "drafts.publish": lambda api, p: api.publish_draft(_path_param(p, "local_id")),
    "publish_queue.list": lambda api, _p: api.list_publish_queue(),
    "publish_queue.retry": lambda api, _p: api.retry_publish_queue(),
    "runs.list": lambda api, _p: api.list_runs(),
    "runs.start": lambda api, p: api.start_run(p),
    "runs.get": lambda api, p: api.get_run(_path_param(p, "run_id")),
    "runs.abort": lambda api, p: api.abort_run(_path_param(p, "run_id")),
}


def encode_frame(envelope: RequestEnvelope | ResponseEnvelope) -> bytes:
    body = envelope.model_dump_json(exclude_none=True).encode("utf-8")
    if len(body) > MAX_FRAME_BYTES:
        raise ValueError("frame too large")
    return struct.pack(">I", len(body)) + body


def decode_frame(data: bytes) -> RequestEnvelope | ResponseEnvelope:
    if len(data) < 4:
        raise ValueError("frame too short")
    (length,) = struct.unpack(">I", data[:4])
    if length > MAX_FRAME_BYTES:
        raise ValueError("frame length exceeds limit")
    body = data[4 : 4 + length]
    payload = json.loads(body.decode("utf-8"))
    if payload.get("ok") is None and "method" in payload:
        return RequestEnvelope.model_validate(payload)
    return ResponseEnvelope.model_validate(payload)


def decode_request_frame(data: bytes) -> RequestEnvelope:
    envelope = decode_frame(data)
    if not isinstance(envelope, RequestEnvelope):
        raise ValueError("expected request envelope")
    return envelope


def decode_response_frame(data: bytes) -> ResponseEnvelope:
    envelope = decode_frame(data)
    if not isinstance(envelope, ResponseEnvelope):
        raise ValueError("expected response envelope")
    return envelope


def success_response(request_id: str, result: Any) -> ResponseEnvelope:
    return ResponseEnvelope(id=request_id, ok=True, result=result)


def error_response(
    request_id: str,
    *,
    code: str,
    message: str,
    status: int = 400,
) -> ResponseEnvelope:
    return ResponseEnvelope(
        id=request_id,
        ok=False,
        error=ErrorBody(code=code, message=message, status=status),
    )


async def dispatch(api: DesktopApi, request: RequestEnvelope) -> ResponseEnvelope:
    if request.v != PROTOCOL_VERSION:
        return error_response(
            request.id,
            code="unsupported_version",
            message=f"protocol v{request.v} not supported",
            status=400,
        )
    handler = METHODS.get(request.method)
    if handler is None:
        return error_response(
            request.id,
            code="unknown_method",
            message=f"unknown method: {request.method}",
            status=404,
        )
    try:
        result = handler(api, request.params)
        if hasattr(result, "__await__"):
            result = await result
        return success_response(request.id, result)
    except DesktopApiError as exc:
        return error_response(
            request.id,
            code=exc.code,
            message=exc.message,
            status=exc.status,
        )
    except Exception as exc:
        return error_response(
            request.id,
            code="internal_error",
            message=str(exc),
            status=500,
        )


async def dispatch_bytes(api: DesktopApi, frame: bytes) -> bytes:
    request = decode_request_frame(frame)
    response = await dispatch(api, request)
    return encode_frame(response)
