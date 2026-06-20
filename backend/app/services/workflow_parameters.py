"""Workflow input parameter validation, masking, and trigger body mapping."""
from __future__ import annotations

import json
from typing import Any, Optional

from app.schemas import ParameterType, WorkflowParameter
from app.services import run_inputs as run_input_svc


class ParameterValidationError(ValueError):
    """Raised when supplied run parameters fail schema validation."""


def mask_secret_value(value: str) -> str:
    if not value:
        return "***"
    tail = value[-2:] if len(value) >= 2 else value
    return f"***{tail}"


def mask_parameters(
    resolved: dict[str, Any],
    declared: list[WorkflowParameter],
) -> dict[str, Any]:
    secret_names = {p.name for p in declared if p.type == "secret"}
    masked_files = run_input_svc.mask_file_parameters(resolved, declared)
    out: dict[str, Any] = {}
    for key, value in masked_files.items():
        if key in secret_names and isinstance(value, str):
            out[key] = mask_secret_value(value)
        else:
            out[key] = value
    return out


def _coerce_value(param: WorkflowParameter, raw: Any) -> Any:
    ptype: ParameterType = param.type
    if ptype == "string":
        if not isinstance(raw, str):
            raise ParameterValidationError(
                f"parameter {param.name!r} expects type string, got {type(raw).__name__}"
            )
        return raw
    if ptype == "number":
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ParameterValidationError(
                f"parameter {param.name!r} expects type number, got {type(raw).__name__}"
            )
        return raw
    if ptype == "boolean":
        if not isinstance(raw, bool):
            raise ParameterValidationError(
                f"parameter {param.name!r} expects type boolean, got {type(raw).__name__}"
            )
        return raw
    if ptype == "secret":
        if not isinstance(raw, str):
            raise ParameterValidationError(
                f"parameter {param.name!r} expects type secret (string), "
                f"got {type(raw).__name__}"
            )
        return raw
    if ptype == "json":
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ParameterValidationError(
                    f"parameter {param.name!r} expects valid JSON"
                ) from exc
        if not isinstance(raw, (dict, list)):
            raise ParameterValidationError(
                f"parameter {param.name!r} expects type json (object or array), "
                f"got {type(raw).__name__}"
            )
        return raw
    if ptype == "file":
        try:
            file_id = run_input_svc.parse_file_param_ref(raw)
        except run_input_svc.RunInputError as exc:
            raise ParameterValidationError(str(exc)) from exc
        return {"file_id": file_id}
    raise ParameterValidationError(f"unknown parameter type {ptype!r}")


def validate_and_resolve_parameters(
    declared: list[WorkflowParameter],
    supplied: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """Validate supplied values, apply defaults, return the resolved parameter map."""
    supplied = supplied or {}
    resolved: dict[str, Any] = {}
    for param in declared:
        if param.name in supplied:
            resolved[param.name] = _coerce_value(param, supplied[param.name])
        elif param.default is not None:
            resolved[param.name] = _coerce_value(param, param.default)
        elif param.required:
            raise ParameterValidationError(
                f"required parameter {param.name!r} is missing"
            )
    return resolved


def split_trigger_body(
    declared: list[WorkflowParameter],
    body: Optional[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Map declared parameter names from a trigger body; passthrough the rest."""
    if not body:
        return {}, {}
    names = {p.name for p in declared}
    mapped = {k: v for k, v in body.items() if k in names}
    passthrough = {k: v for k, v in body.items() if k not in names}
    return mapped, passthrough


def load_resolved_parameters_json(raw: Optional[str]) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


__all__ = [
    "ParameterValidationError",
    "mask_secret_value",
    "mask_parameters",
    "validate_and_resolve_parameters",
    "split_trigger_body",
    "load_resolved_parameters_json",
]
