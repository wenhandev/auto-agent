from __future__ import annotations

import copy
import json
import logging
import re
import uuid
from typing import Any, Optional

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.agents.model import get_adk_model
from app.schemas import Workflow as WorkflowSchema


logger = logging.getLogger(__name__)


_APP_NAME = "auto-agent-editor"

_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_-]*\s*\n?|\n?```\s*$")


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = _FENCE_RE.sub("", cleaned).strip()
    return cleaned


EDITOR_INSTRUCTION = """\
You are a workflow editor. You receive the current Workflow JSON and a user
instruction. Output ONE JSON object (no prose, no code fences) with these keys:

- "assistant_message": short Chinese explanation (one sentence).
- "patch": optional list of ops (preferred when changes are < 30% of nodes).
- "full_workflow": optional complete Workflow JSON.

Set AT MOST one of "patch" / "full_workflow". If purely conversational, set
both to null.

Patch op formats:
  {"op":"add_node","node":{"id","type","label","params"}}
  {"op":"remove_node","id":"<node id>"}
  {"op":"update_node","id":"<node id>","patch":{"label"?,"type"?,"params"?}}
  {"op":"add_edge","edge":{"id","source","target","when"?}}
  {"op":"remove_edge","id":"<edge id>"}
  {"op":"set_start","id":"<node id>"}

Node types and params:
  start:        params: { }
  end:          params: { }
  navigate:     params: { "url": str }
  click:        params: { "selector": str }
  fill:         params: { "selector": str, "value": str }
  wait:         params: { "ms": int }
  extract:      params: { "instruction": str }
  fuzzy_action: params: { "instruction": str }
  condition:    params: { "expr": str }    (outgoing edges set when="true"/"false")

Rules:
- Reuse existing node/edge ids; introduce new ones with prefixes nX / eX where
  X is the next free integer.
- Keep labels in the user's vocabulary (Chinese if they wrote Chinese).
- When adding a node, also add an edge wiring it into the graph unless the
  user only asked for a disconnected node.
- For "wait" nodes, params.ms is an integer of milliseconds.
- Workflow JSON is {nodes:[...], edges:[...], start_id:"<id>"}.

Respond with ONLY the JSON object.
"""


class EditorResponse(BaseModel):
    assistant_message: str
    patch: Optional[list[dict[str, Any]]] = None
    full_workflow: Optional[dict[str, Any]] = None


def _apply_op(workflow: dict, op: dict) -> None:
    op_type = op.get("op")
    nodes = workflow["nodes"]
    edges = workflow["edges"]
    if op_type == "add_node":
        node = op.get("node")
        if not isinstance(node, dict) or "id" not in node:
            raise ValueError("add_node requires a 'node' object with id")
        if any(n["id"] == node["id"] for n in nodes):
            raise ValueError(f"add_node: duplicate node id {node['id']!r}")
        nodes.append(node)
    elif op_type == "remove_node":
        nid = op.get("id")
        if not nid:
            raise ValueError("remove_node requires 'id'")
        if not any(n["id"] == nid for n in nodes):
            raise ValueError(f"remove_node: unknown node id {nid!r}")
        workflow["nodes"] = [n for n in nodes if n["id"] != nid]
        workflow["edges"] = [
            e for e in edges if e.get("source") != nid and e.get("target") != nid
        ]
    elif op_type == "update_node":
        nid = op.get("id")
        patch = op.get("patch") or {}
        if not nid:
            raise ValueError("update_node requires 'id'")
        for n in nodes:
            if n["id"] == nid:
                if "label" in patch:
                    n["label"] = patch["label"]
                if "type" in patch:
                    n["type"] = patch["type"]
                if "params" in patch:
                    merged = dict(n.get("params") or {})
                    merged.update(patch["params"] or {})
                    n["params"] = merged
                break
        else:
            raise ValueError(f"update_node: unknown node id {nid!r}")
    elif op_type == "add_edge":
        edge = op.get("edge")
        if not isinstance(edge, dict) or "id" not in edge:
            raise ValueError("add_edge requires an 'edge' object with id")
        if any(e["id"] == edge["id"] for e in edges):
            raise ValueError(f"add_edge: duplicate edge id {edge['id']!r}")
        edges.append(edge)
    elif op_type == "remove_edge":
        eid = op.get("id")
        if not eid:
            raise ValueError("remove_edge requires 'id'")
        if not any(e["id"] == eid for e in edges):
            raise ValueError(f"remove_edge: unknown edge id {eid!r}")
        workflow["edges"] = [e for e in edges if e["id"] != eid]
    elif op_type == "set_start":
        nid = op.get("id")
        if not nid:
            raise ValueError("set_start requires 'id'")
        if not any(n["id"] == nid for n in nodes):
            raise ValueError(f"set_start: unknown node id {nid!r}")
        workflow["start_id"] = nid
    else:
        raise ValueError(f"unknown op {op_type!r}")


def apply_patch(current_workflow_json: dict, patch: list[dict]) -> dict:
    new = copy.deepcopy(current_workflow_json)
    for op in patch:
        _apply_op(new, op)
    WorkflowSchema.model_validate(new)
    return new


class EditorAgent:
    def __init__(self) -> None:
        self._agent = LlmAgent(
            name="editor",
            model=get_adk_model(),
            instruction=EDITOR_INSTRUCTION,
        )
        self._session_service = InMemorySessionService()
        self._runner = Runner(
            app_name=_APP_NAME,
            agent=self._agent,
            session_service=self._session_service,
        )

    async def _run_once(self, prompt: str) -> str:
        user_id = "editor-user"
        session_id = f"editor-{uuid.uuid4().hex[:12]}"
        await self._session_service.create_session(
            app_name=_APP_NAME, user_id=user_id, session_id=session_id
        )
        message = types.Content(role="user", parts=[types.Part(text=prompt)])
        final_text = ""
        async for event in self._runner.run_async(
            user_id=user_id, session_id=session_id, new_message=message
        ):
            if event.is_final_response() and event.content and event.content.parts:
                for p in event.content.parts:
                    if getattr(p, "text", None):
                        final_text += p.text
        return final_text.strip()

    def _build_prompt(
        self,
        current_workflow_json: dict,
        history: list[tuple[str, str]],
        user_message: str,
    ) -> str:
        history_text = ""
        for role, content in history[-20:]:
            history_text += f"\n[{role}] {content}"
        return (
            "Current Workflow JSON:\n"
            + json.dumps(current_workflow_json, ensure_ascii=False)
            + ("\n\nConversation so far:" + history_text if history_text else "")
            + "\n\nUser request:\n"
            + user_message.strip()
        )

    async def edit(
        self,
        current_workflow_json: dict,
        history: list[tuple[str, str]],
        user_message: str,
    ) -> EditorResponse:
        prompt = self._build_prompt(current_workflow_json, history, user_message)
        text = _strip_code_fences(await self._run_once(prompt))
        try:
            return EditorResponse.model_validate_json(text)
        except ValidationError as exc:
            retry_prompt = (
                prompt
                + "\n\n(Previous output was not a valid response. Validation error:\n"
                + str(exc)
                + "\nReturn ONLY one JSON object matching the schema.)"
            )
            text2 = _strip_code_fences(await self._run_once(retry_prompt))
            return EditorResponse.model_validate_json(text2)


__all__ = [
    "EditorAgent",
    "EditorResponse",
    "apply_patch",
    "EDITOR_INSTRUCTION",
]
