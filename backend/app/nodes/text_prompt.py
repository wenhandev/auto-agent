from __future__ import annotations

import json
import logging
from typing import Any, Optional

from google.genai import types

from app.agents.vision import _validate_json_schema
from app.nodes.result import Item
from app.services import artifact_context
from app.services import cost_tracking as cost_svc
from app.settings import llm_is_configured

logger = logging.getLogger(__name__)


async def _call_llm(*, prompt: str, system: str | None) -> str:
    from app.agents.model import get_genai_client, get_genai_model_id

    from app.services import llm_traces as trace_svc

    client = get_genai_client()
    model_id = get_genai_model_id()
    config = types.GenerateContentConfig(
        system_instruction=system or "You are a helpful assistant."
    )
    with trace_svc.LlmCallTracer() as tracer:
        response = await client.aio.models.generate_content(
            model=model_id, contents=prompt, config=config
        )
    usage = cost_svc.usage_from_genai_response(response)
    text = (getattr(response, "text", None) or "").strip()
    run_id = artifact_context.get_run_id()
    if run_id:
        trace_svc.record_llm_trace(
            model=model_id,
            system=system or "You are a helpful assistant.",
            messages=[{"role": "user", "content": prompt}],
            response=text,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            latency_ms=tracer.latency_ms,
        )
        cost_svc.record_llm_usage(
            run_id,
            model=model_id,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            node_id=artifact_context.get_node_id(),
        )
    return text


async def _repair_json(
    raw: str,
    schema: dict[str, Any],
    *,
    prompt: str,
    error: str,
) -> Optional[Any]:
    repair_prompt = (
        f"The following model output did not match the schema.\n"
        f"Original prompt: {prompt}\n"
        f"Schema: {json.dumps(schema, ensure_ascii=False)}\n"
        f"Validation error: {error}\n"
        f"Raw output: {raw}\n"
        "Return ONLY valid JSON matching the schema."
    )
    try:
        text = await _call_llm(prompt=repair_prompt, system="You repair JSON to match a JSON Schema.")
        return json.loads(text)
    except Exception as exc:
        logger.warning("text_prompt schema repair failed: %s", exc)
        return None


async def run(
    params: dict[str, Any],
    *,
    input_items: list[Item],
    context: dict[str, Any],
) -> list[Item]:
    prompt = str(params.get("prompt", "")).strip()
    if not prompt:
        raise ValueError("text_prompt requires non-empty prompt")

    system = params.get("system")
    schema = params.get("schema")
    if schema is not None and not isinstance(schema, dict):
        schema = None

    if not llm_is_configured():
        stub = {"text": f"[stub] {prompt[:120]}"}
        if schema:
            stub = {"stub": True, "prompt": prompt[:120]}
        return [Item(json=stub)]

    raw = await _call_llm(prompt=prompt, system=str(system) if system else None)

    if not schema:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"text": raw}
        return [Item(json=data)]

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        repaired = await _repair_json(raw, schema, prompt=prompt, error="invalid JSON")
        if repaired is None:
            raise ValueError("schema_validation_failed: invalid JSON")
        data = repaired

    ok, err = _validate_json_schema(data, schema)
    if not ok:
        repaired = await _repair_json(raw, schema, prompt=prompt, error=err)
        if repaired is None:
            raise ValueError(f"schema_validation_failed: {err}")
        data = repaired
        ok, err = _validate_json_schema(data, schema)
        if not ok:
            raise ValueError(f"schema_validation_failed: {err}")

    return [Item(json=data)]
