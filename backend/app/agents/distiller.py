"""Optional LLM distillation of recorded traces into workflow graphs."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Optional

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import ValidationError

from app.agents.model import get_adk_model
from app.settings import llm_is_configured
from app.agents.synthesizer import trace_to_graph, validate_workflow_graph
from app.schemas import Workflow

DISTILLER_INSTRUCTION = """\
You convert a browser action trace (JSON list of events) into a strict Workflow JSON.
Use the same node vocabulary as the workflow planner:
start, end, navigate, click, fill, wait, extract, vision_navigate, vision_act,
desktop_open, desktop_act, desktop_navigate, desktop_extract,
vision_extract, login, condition, switch, approval.

Rules:
- Drop scroll/wait noise.
- Prefer vision_act when selectors are missing or ambiguous.
- Convert sensitive fills into a login node (credential placeholder SELECT_CREDENTIAL).
- Keep labels in the user's language when event descriptions are Chinese.
- Return ONLY the Workflow JSON object — no prose, no code fences.
"""

_APP_NAME = "auto-agent-distiller"
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_code_fences(text: str) -> str:
    return _FENCE_RE.sub("", text.strip()).strip()


class DistillerAgent:
    def __init__(self) -> None:
        self._session_service = InMemorySessionService()
        self._agent = LlmAgent(
            model=get_adk_model(),
            name="distiller",
            instruction=DISTILLER_INSTRUCTION,
            output_schema=Workflow,
        )
        self._runner = Runner(
            agent=self._agent,
            app_name=_APP_NAME,
            session_service=self._session_service,
        )

    async def _run_once(self, payload: str) -> str:
        user_id = "distiller-user"
        session_id = f"distiller-{uuid.uuid4().hex[:12]}"
        await self._session_service.create_session(
            app_name=_APP_NAME, user_id=user_id, session_id=session_id
        )
        message = types.Content(role="user", parts=[types.Part(text=payload)])
        final_text = ""
        async for event in self._runner.run_async(
            user_id=user_id, session_id=session_id, new_message=message
        ):
            if event.is_final_response() and event.content and event.content.parts:
                for part in event.content.parts:
                    if getattr(part, "text", None):
                        final_text += part.text
        return final_text.strip()

    async def distill(self, events: list[dict[str, Any]]) -> Workflow:
        payload = json.dumps(events, ensure_ascii=False)
        text = _strip_code_fences(await self._run_once(payload))
        try:
            return Workflow.model_validate_json(text)
        except ValidationError as exc:
            retry = (
                payload
                + "\n\nPrevious output failed validation:\n"
                + str(exc)
                + "\nReturn ONLY valid Workflow JSON."
            )
            text2 = _strip_code_fences(await self._run_once(retry))
            return Workflow.model_validate_json(text2)


async def distill_workflow_graph(
    events: list[dict[str, Any]],
    *,
    recording_name: Optional[str] = None,
) -> tuple[dict[str, Any], str]:
    """Return (workflow_graph, mode). Falls back to rule-based synthesis."""
    if not llm_is_configured():
        graph = trace_to_graph(events, recording_name=recording_name)
        validate_workflow_graph(graph)
        return graph, "rule"

    try:
        agent = DistillerAgent()
        workflow = await agent.distill(events)
        graph = workflow.model_dump()
        validate_workflow_graph(graph)
        return graph, "llm"
    except Exception:
        graph = trace_to_graph(events, recording_name=recording_name)
        validate_workflow_graph(graph)
        return graph, "rule"


__all__ = ["DistillerAgent", "distill_workflow_graph"]
