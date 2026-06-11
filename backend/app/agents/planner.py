from __future__ import annotations

# Planner uses ADK's `LlmAgent` to convert a natural-language description
# into a strict `Workflow` JSON. We deliberately split the schema-enforcement
# strategy by provider:
#
# - `openai` (LiteLlm): pass `output_schema=Workflow` so the gateway can use
#   structured-output / JSON-schema mode.
# - `google` / `gemini` (native protocol): do NOT pass `output_schema`. The
#   Gemini API's `response_schema` validator rejects pydantic's
#   `additionalProperties: true` (emitted by `Node.params: dict[str, Any]`)
#   with "additionalProperties is not supported in the Gemini API." Instead
#   we steer the model with a strict prompt + few-shot, then parse the
#   returned text into `Workflow`. ADK still forbids tool use when
#   `output_schema` is set, so we keep tools off for both branches and rely
#   on `Workflow.model_validate_json` to enforce the schema after the fact.

import re
import uuid

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types
from pydantic import ValidationError

from app.agents.model import get_adk_model
from app.schemas import Workflow
from app.settings import settings


PLANNER_INSTRUCTION = """\
You convert a natural-language description of a browser-automation task into a
strict JSON `Workflow`. The output is parsed against this schema:

Workflow = {
  "nodes": [Node, ...],
  "edges": [Edge, ...],
  "start_id": <string id of the first node>
}

Node = { "id": str, "type": NodeType, "label": str (in the user's language),
         "params": dict }
Edge = { "id": str, "source": str, "target": str,
         "when": "true" | "false" | null }

Allowed NodeType values and their params:
  - "start"        params: {}
  - "end"          params: {}
  - "navigate"     params: { "url": str }
  - "click"        params: { "selector": str }
  - "fill"         params: { "selector": str, "value": str }
  - "wait"         params: { "ms": int }
  - "extract"      params: { "instruction": str }
  - "fuzzy_action" params: { "instruction": str }
  - "condition"    params: { "expr": str }      # outgoing edges set when="true"/"false"

RULES
- Use the user's vocabulary verbatim in each `label` (Chinese or English).
- One user-perceivable step per node. Keep the graph small.
- Prefer deterministic types ("navigate", "click", "fill", "wait", "extract")
  when the description is precise.
- Use "fuzzy_action" only when the step requires perception/judgment ("find the
  ...", "decide which ...", "analyze the page ...").
- Always set `start_id` and connect every non-end node with an outgoing edge.
- Node ids must be unique; reuse them in edges. Edge ids must be unique too.

EXAMPLES

Description: 打开 https://example.com 然后等待 500ms 再点击页面上的「更多」按钮
Output:
{"nodes":[
  {"id":"n1","type":"navigate","label":"打开 example.com","params":{"url":"https://example.com"}},
  {"id":"n2","type":"wait","label":"等待 500ms","params":{"ms":500}},
  {"id":"n3","type":"click","label":"点击「更多」按钮","params":{"selector":"text=更多"}}
 ],
 "edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"}
 ],
 "start_id":"n1"}

Description: 打开示例页面,分析页面找到主标题,然后跳转到 example.org
Output:
{"nodes":[
  {"id":"n1","type":"navigate","label":"打开示例页面","params":{"url":"https://example.com"}},
  {"id":"n2","type":"fuzzy_action","label":"分析页面找到主标题","params":{"instruction":"找到 h1 主标题文字"}},
  {"id":"n3","type":"navigate","label":"跳转到 example.org","params":{"url":"https://example.org"}}
 ],
 "edges":[
  {"id":"e1","source":"n1","target":"n2"},
  {"id":"e2","source":"n2","target":"n3"}
 ],
 "start_id":"n1"}

Respond with ONLY the JSON object — no prose, no code fences.
"""


_APP_NAME = "auto-agent-planner"

_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_-]*\s*\n?|\n?```\s*$")


def _strip_code_fences(text: str) -> str:
    """Tolerate models that wrap JSON in ```json ... ``` despite the prompt."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = _FENCE_RE.sub("", cleaned).strip()
    return cleaned


class PlannerAgent:
    def __init__(self) -> None:
        provider = (settings.llm_provider or "openai").lower()
        self._uses_native_gemini = provider in ("google", "gemini")

        agent_kwargs: dict = {
            "name": "planner",
            "model": get_adk_model(),
            "instruction": PLANNER_INSTRUCTION,
        }
        if not self._uses_native_gemini:
            agent_kwargs["output_schema"] = Workflow

        self._agent = LlmAgent(**agent_kwargs)
        self._session_service = InMemorySessionService()
        self._runner = Runner(
            app_name=_APP_NAME,
            agent=self._agent,
            session_service=self._session_service,
        )

    def _check_api_key(self) -> None:
        provider = (settings.llm_provider or "openai").lower()
        if provider == "openai" and not settings.openai_api_key:
            raise RuntimeError(
                "LLM API key not configured for provider 'openai' "
                "(set OPENAI_API_KEY in .env)"
            )
        if provider in ("google", "gemini") and not settings.google_api_key:
            raise RuntimeError(
                "LLM API key not configured for provider 'google' "
                "(set GOOGLE_API_KEY in .env)"
            )

    async def _run_once(self, description: str) -> str:
        user_id = "planner-user"
        session_id = f"planner-{uuid.uuid4().hex[:12]}"
        await self._session_service.create_session(
            app_name=_APP_NAME, user_id=user_id, session_id=session_id
        )
        message = types.Content(
            role="user", parts=[types.Part(text=description.strip())]
        )
        final_text = ""
        async for event in self._runner.run_async(
            user_id=user_id, session_id=session_id, new_message=message
        ):
            if event.is_final_response() and event.content and event.content.parts:
                for p in event.content.parts:
                    if getattr(p, "text", None):
                        final_text += p.text
        return final_text.strip()

    async def generate_workflow(self, description: str) -> Workflow:
        self._check_api_key()
        text = _strip_code_fences(await self._run_once(description))
        try:
            return Workflow.model_validate_json(text)
        except ValidationError as exc:
            retry_hint = (
                description
                + "\n\n(Previous output was not a valid `Workflow` JSON object."
                f" Validation error:\n{exc}\n"
                "Return ONLY the JSON object — no prose, no code fences.)"
            )
            text2 = _strip_code_fences(await self._run_once(retry_hint))
            return Workflow.model_validate_json(text2)
