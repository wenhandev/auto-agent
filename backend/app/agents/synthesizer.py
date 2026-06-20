"""Rule-based workflow synthesis from recorded action traces.

An optional LLM path can be added later; MVP uses deterministic mapping with
vision fallbacks where targets are ambiguous.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional
from uuid import uuid4

from sqlmodel import Session

from app.db.models import ChatMessage, Recording, Workflow
from app.schemas import Workflow as WorkflowSchema
from app.services import workflows as workflow_svc
from app.services.recording import load_events

_SYNTH_MARKER = "[recorded-synthesized draft — review before scheduling]"
_SEED_CHAT_MESSAGE = "我录制了这个流程，请帮我细化"
_LOGIN_CREDENTIAL_PLACEHOLDER = "SELECT_CREDENTIAL"


def _node_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip().lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug or not slug[0].isalpha():
        slug = f"param_{slug}" if slug else "param_value"
    return slug[:48]


def _infer_param_name(event: dict[str, Any]) -> str:
    for key in ("description", "name", "selector"):
        raw = event.get(key)
        if isinstance(raw, str) and raw.strip():
            return _slugify(raw)
    return "input_value"


def _is_unambiguous_selector(selector: Optional[str]) -> bool:
    return bool(selector and isinstance(selector, str) and selector.startswith("#"))


def _should_use_vision(event: dict[str, Any]) -> bool:
    if event.get("type") in ("scroll", "wait"):
        return False
    if event.get("type") == "navigate":
        return False
    if event.get("type") == "click" and not _is_unambiguous_selector(event.get("selector")):
        return True
    if event.get("type") == "fill" and not _is_unambiguous_selector(event.get("selector")):
        return True
    if event.get("type") == "select":
        return not _is_unambiguous_selector(event.get("selector"))
    return False


def trace_to_graph(
    events: list[dict[str, Any]],
    *,
    recording_name: Optional[str] = None,
) -> dict[str, Any]:
    """Convert a recorded trace into workflow JSON (nodes, edges, parameters)."""
    nodes: list[dict[str, Any]] = [
        {"id": "start", "type": "start", "label": "开始", "params": {}},
    ]
    edges: list[dict[str, Any]] = []
    parameters: list[dict[str, Any]] = []
    seen_params: set[str] = set()
    prev_id = "start"
    login_emitted = False

    for event in events:
        event_type = event.get("type")
        if event_type in ("scroll", "wait"):
            continue

        node_id = _node_id(str(event_type or "step"))
        label = event.get("description") or event_type or "step"
        screenshot_ref = event.get("screenshot_ref")
        node_meta: dict[str, Any] = {}
        if screenshot_ref:
            node_meta["screenshot_ref"] = screenshot_ref

        if event_type == "navigate" and event.get("url"):
            url = event["url"]
            nodes.append({
                "id": node_id,
                "type": "navigate",
                "label": f"打开 {url}",
                "params": {"url": url},
                **({"meta": node_meta} if node_meta else {}),
            })
        elif event.get("sensitive") and event_type == "fill":
            if not login_emitted:
                nodes.append({
                    "id": node_id,
                    "type": "login",
                    "label": "登录",
                    "params": {
                        "credential": _LOGIN_CREDENTIAL_PLACEHOLDER,
                        "url": event.get("url"),
                    },
                    **({"meta": node_meta} if node_meta else {}),
                })
                login_emitted = True
            else:
                continue
        elif event_type == "fill":
            if _should_use_vision(event):
                instruction = f"在 {label or '输入框'} 中填写内容"
                nodes.append({
                    "id": node_id,
                    "type": "vision_act",
                    "label": label,
                    "params": {"instruction": instruction},
                    **({"meta": node_meta} if node_meta else {}),
                })
            else:
                param_name = _infer_param_name(event)
                if param_name not in seen_params and event.get("value") is not None:
                    parameters.append({
                        "name": param_name,
                        "type": "string",
                        "label": label,
                        "default": event.get("value"),
                    })
                    seen_params.add(param_name)
                nodes.append({
                    "id": node_id,
                    "type": "fill",
                    "label": label,
                    "params": {
                        "selector": event.get("selector") or "",
                        "value": f"{{{{params.{param_name}}}}}",
                    },
                    **({"meta": node_meta} if node_meta else {}),
                })
        elif event_type == "click":
            if _should_use_vision(event):
                instruction = label or "点击目标元素"
                nodes.append({
                    "id": node_id,
                    "type": "vision_act",
                    "label": label,
                    "params": {"instruction": instruction},
                    **({"meta": node_meta} if node_meta else {}),
                })
            else:
                nodes.append({
                    "id": node_id,
                    "type": "click",
                    "label": label,
                    "params": {"selector": event.get("selector") or ""},
                    **({"meta": node_meta} if node_meta else {}),
                })
        elif event_type == "select":
            if _should_use_vision(event):
                nodes.append({
                    "id": node_id,
                    "type": "vision_act",
                    "label": label,
                    "params": {"instruction": f"选择 {event.get('value') or label}"},
                    **({"meta": node_meta} if node_meta else {}),
                })
            else:
                nodes.append({
                    "id": node_id,
                    "type": "fill",
                    "label": label,
                    "params": {
                        "selector": event.get("selector") or "",
                        "value": str(event.get("value") or ""),
                    },
                    **({"meta": node_meta} if node_meta else {}),
                })
        else:
            nodes.append({
                "id": node_id,
                "type": "vision_act",
                "label": label,
                "params": {"instruction": label},
                **({"meta": node_meta} if node_meta else {}),
            })

        edges.append({
            "id": f"e_{prev_id}_{node_id}",
            "source": prev_id,
            "target": node_id,
        })
        prev_id = node_id

    end_id = "end"
    nodes.append({"id": end_id, "type": "end", "label": "结束", "params": {}})
    edges.append({"id": f"e_{prev_id}_{end_id}", "source": prev_id, "target": end_id})

    return {
        "nodes": nodes,
        "edges": edges,
        "start_id": "start",
        "parameters": parameters,
    }


def validate_workflow_graph(graph: dict[str, Any]) -> WorkflowSchema:
    return WorkflowSchema.model_validate(graph)


def synthesize_from_recording(
    recording: Recording,
    session: Session,
    *,
    workflow_name: Optional[str] = None,
) -> tuple[str, dict[str, Any], str]:
    """Build draft workflow + seeded chat from a stopped recording."""
    events = load_events(recording)
    graph = trace_to_graph(events, recording_name=recording.name)
    validate_workflow_graph(graph)

    name = workflow_name or f"Draft: {recording.name or recording.id[:8]}"
    description = f"{_SYNTH_MARKER}\n\nSource recording: {recording.id}"

    workflow = workflow_svc.create_workflow(
        name=name,
        session=session,
        description=description,
        initial_workflow_json=graph,
        authored_by="planner",
    )
    row = session.get(Workflow, workflow.id)
    if row is not None:
        row.status = "draft"
        session.add(row)

    chat = workflow_svc.ensure_chat_session(workflow.id, session)
    seed = ChatMessage(
        session_id=chat.id,
        role="user",
        content=_SEED_CHAT_MESSAGE,
        created_at=workflow.created_at,
    )
    session.add(seed)

    recording.generated_workflow_id = workflow.id
    recording.generated_workflow_json = json.dumps(graph, ensure_ascii=False)
    recording.status = "synthesized"
    session.add(recording)
    session.commit()
    session.refresh(recording)
    session.refresh(workflow)

    return workflow.id, graph, chat.id


async def synthesize_with_llm(
    recording: Recording,
    session: Session,
    *,
    workflow_name: Optional[str] = None,
) -> tuple[str, dict[str, Any], str]:
    """LLM synthesis hook — falls back to rule-based graph for MVP."""
    return synthesize_from_recording(
        recording, session, workflow_name=workflow_name
    )


__all__ = [
    "trace_to_graph",
    "validate_workflow_graph",
    "synthesize_from_recording",
    "synthesize_with_llm",
    "_SYNTH_MARKER",
    "_LOGIN_CREDENTIAL_PLACEHOLDER",
]
