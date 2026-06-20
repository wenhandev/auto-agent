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
from app.integrations.catalogue_prompt import integration_catalogue_prompt
from app.schemas import Workflow
from app.settings import llm_is_configured, settings


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
  - "vision_navigate" params: { "goal": str, "max_steps"?: int, "success_criteria"?: str }
  - "vision_act"   params: { "instruction": str }
  - "vision_extract" params: { "instruction": str, "schema"?: object }
  - "fuzzy_action" params: { "instruction": str }  # alias of vision_navigate
  - "condition"    params: { "expr": str } OR { "predicate": { "left", "op", "right"? } }
                   # IF/ELSE flow branch — outgoing edges use when="true"/"false"
  - "switch"       params: { "expr": str }      # multi-way branch — edges use case="..."
                   # use switch for 3+ paths; use filter to shrink item lists (not flow skip)
  - "approval"     params: { "prompt": str, "inputs"?: [{name,type,required?,default?,label?}],
                               "approve_label"?: str, "reject_label"?: str }
                   # pauses the run until an operator approves or rejects
  - "login"        params: { "credential": str, "url"?: str, "success_criteria"?: str,
                               "totp_identifier"?: str }
                   # authenticates via vision using a linked credential; prefer over
                   # hand-rolled fill/click login sequences
""" + integration_catalogue_prompt() + """

Example approval node before a risky click:
{"id":"n_confirm","type":"approval","label":"确认继续？","params":{"prompt":"确认继续？","inputs":[{"name":"note","type":"string","required":true}]}}

RULES
- Use the user's vocabulary verbatim in each `label` (Chinese or English).
- One user-perceivable step per node. Keep the graph small.
- Prefer vision primitives ("vision_navigate", "vision_act", "vision_extract") when
  the step needs perception or judgment — selectors in click/fill are optional hints.
- Use a "login" node (not fill/click chains) when the workflow must authenticate.
- Use deterministic types ("navigate", "click", "fill", "wait", "extract") when the
  description is precise and selectors are known.
- Use "fuzzy_action" only for backward compatibility (same as vision_navigate).
- Use **condition** (IF) when the workflow must take one of two paths based on data
  (e.g. HTTP status >= 400 → error path). Connect with when="true" and when="false" edges.
- Use **switch** when branching into three or more cases (e.g. status paid/pending/failed).
- Use **filter** to remove items from a list inside a data pipeline — NOT to skip steps.
- Always set `start_id` and connect every non-end node with an outgoing edge.
- Node ids must be unique; reuse them in edges. Edge ids must be unique too.

ERROR HANDLING
Each node may declare a retry policy ({max_attempts, backoff_ms}) and a failure
policy on_error ∈ {"fail_run", "continue", "branch"}. Edges may carry
kind="on_error" to be followed when the source node's on_error="branch" and it
failed. Example: a flaky click node n4 with retry={max_attempts:3, backoff_ms:500}
and on_error="branch", plus an edge {source:"n4", target:"cleanup_n9",
kind:"on_error"}, will retry the click up to 3 times, then route to cleanup_n9
if all attempts fail.

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

Description: 打开示例页面,找到主标题并提取为 JSON
Output:
{"nodes":[
  {"id":"n1","type":"navigate","label":"打开示例页面","params":{"url":"https://example.com"}},
  {"id":"n2","type":"vision_extract","label":"提取主标题","params":{"instruction":"页面 h1 主标题","schema":{"type":"object","properties":{"title":{"type":"string"}},"required":["title"]}}},
  {"id":"n3","type":"vision_act","label":"点击更多","params":{"instruction":"点击 More 链接"}}
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
  {"id":"n2","type":"vision_navigate","label":"分析页面找到主标题","params":{"goal":"找到 h1 主标题文字"}},
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
        if provider in ("google", "gemini") and not llm_is_configured():
            raise RuntimeError(
                "LLM API key not configured for provider 'google' "
                "(set GOOGLE_API_KEY in .env, or GEMINI_PROVIDER=vertex + GCP_PROJECT)"
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
