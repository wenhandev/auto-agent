"""Worker-authenticated LLM proxy (cloud holds API keys)."""

from __future__ import annotations

import base64
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.worker_auth import WorkerAuth, require_worker_session


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/llm", tags=["internal"])


class LlmCompleteRequest(BaseModel):
    purpose: str = "general"
    messages: list[dict[str, Any]] = Field(default_factory=list)
    system_instruction: Optional[str] = None
    image_b64: Optional[str] = None
    image_mime: Optional[str] = "image/png"


class LlmCompleteResponse(BaseModel):
    text: str


def _extract_response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text:
        return text.strip()
    parts_text: list[str] = []
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            value = getattr(part, "text", None)
            if isinstance(value, str) and value:
                parts_text.append(value)
    return "\n".join(parts_text).strip()


@router.post("/complete", response_model=LlmCompleteResponse)
async def llm_complete(
    body: LlmCompleteRequest,
    _auth: WorkerAuth = Depends(require_worker_session),
) -> LlmCompleteResponse:
    from app.settings import settings

    provider = (settings.llm_provider or "openai").lower()
    try:
        if provider in ("google", "gemini"):
            from google.genai import types

            from app.agents.model import get_genai_client, get_genai_model_id

            client = get_genai_client()
            model_id = get_genai_model_id()
            parts: list[Any] = []
            if body.image_b64:
                raw = base64.b64decode(body.image_b64)
                parts.append(
                    types.Part.from_bytes(
                        data=raw,
                        mime_type=body.image_mime or "image/png",
                    )
                )
            user_text = "\n".join(
                str(m.get("content") or "")
                for m in body.messages
                if m.get("role") in ("user", None)
            )
            if user_text:
                parts.append(types.Part.from_text(text=user_text))
            contents = [types.Content(role="user", parts=parts or [types.Part.from_text(text="")])]
            config = None
            if body.system_instruction:
                config = types.GenerateContentConfig(system_instruction=body.system_instruction)
            response = await client.aio.models.generate_content(
                model=model_id,
                contents=contents,
                config=config,
            )
            return LlmCompleteResponse(text=_extract_response_text(response))

        from litellm import acompletion

        from app.services.llm_runtime import effective_settings

        eff = effective_settings()
        litellm_messages: list[dict[str, str]] = []
        if body.system_instruction:
            litellm_messages.append({"role": "system", "content": body.system_instruction})
        for msg in body.messages:
            role = str(msg.get("role") or "user")
            if role not in ("system", "user", "assistant"):
                role = "user"
            litellm_messages.append({"role": role, "content": str(msg.get("content") or "")})
        kwargs: dict[str, Any] = {
            "model": f"openai/{eff.model}",
            "messages": litellm_messages,
        }
        if eff.api_key:
            kwargs["api_key"] = eff.api_key
        if eff.base_url:
            kwargs["api_base"] = eff.base_url
        result = await acompletion(**kwargs)
        choice = result.choices[0]
        text = choice.message.content if choice.message else ""
        return LlmCompleteResponse(text=str(text or ""))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("llm proxy failed purpose=%s", body.purpose)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


__all__ = ["router"]
