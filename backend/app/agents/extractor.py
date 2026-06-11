from __future__ import annotations

import logging
from typing import Any, Optional

from google.genai import types
from playwright.async_api import Page

from app.agents.model import get_genai_client, get_genai_model_id


logger = logging.getLogger(__name__)


_PAGE_TEXT_LIMIT = 8_000

_SYSTEM_INSTRUCTION = "You extract structured data from web pages."


def _build_user_prompt(text: str, instruction: str) -> str:
    return (
        f"Page text:\n{text}\n\n"
        f"Instruction: {instruction}\n"
        "Respond ONLY with the extracted value as plain text. If the page "
        "does not contain the answer, respond with NOT_FOUND."
    )


async def _collect_page_text(page: Page) -> str:
    try:
        text = await page.inner_text("body")
    except Exception:
        text = ""
    text = text.strip()
    if len(text) > _PAGE_TEXT_LIMIT:
        text = text[:_PAGE_TEXT_LIMIT] + "\n…[truncated]"
    return text


async def _grab_screenshot(page: Page) -> Optional[bytes]:
    try:
        return await page.screenshot(full_page=False)
    except Exception as exc:
        logger.warning("extractor: screenshot failed (%s)", exc)
        return None


def _extract_response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text:
        return text.strip()
    parts_text: list[str] = []
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            value = getattr(part, "text", None)
            if isinstance(value, str) and value:
                parts_text.append(value)
    return "\n".join(parts_text).strip()


async def _call_with_vision(
    client: Any, model_id: str, user_prompt: str, screenshot: bytes
) -> Any:
    parts = [
        types.Part.from_bytes(data=screenshot, mime_type="image/png"),
        types.Part.from_text(text=user_prompt),
    ]
    contents = [types.Content(role="user", parts=parts)]
    config = types.GenerateContentConfig(system_instruction=_SYSTEM_INSTRUCTION)
    return await client.aio.models.generate_content(
        model=model_id, contents=contents, config=config
    )


async def _call_text_only(client: Any, model_id: str, user_prompt: str) -> Any:
    config = types.GenerateContentConfig(system_instruction=_SYSTEM_INSTRUCTION)
    return await client.aio.models.generate_content(
        model=model_id, contents=user_prompt, config=config
    )


async def extract_from_page(page: Page, instruction: str) -> dict:
    page_url = page.url
    try:
        page_title = await page.title()
    except Exception:
        page_title = ""

    base: dict[str, Any] = {
        "instruction": instruction,
        "page_url": page_url,
        "page_title": page_title,
    }

    text = await _collect_page_text(page)
    user_prompt = _build_user_prompt(text=text, instruction=instruction)
    screenshot = await _grab_screenshot(page)

    try:
        client = get_genai_client()
        model_id = get_genai_model_id()
    except RuntimeError as exc:
        logger.warning("extractor: client unavailable (%s)", exc)
        return {**base, "text": None, "error": str(exc)}

    response = None
    if screenshot is not None:
        try:
            response = await _call_with_vision(
                client, model_id, user_prompt, screenshot
            )
        except Exception as exc:
            logger.warning(
                "extractor: vision call failed (%s); falling back to text-only",
                exc,
            )
            response = None

    if response is None:
        try:
            response = await _call_text_only(client, model_id, user_prompt)
        except Exception as exc:
            logger.exception("extractor: text-only call failed")
            return {**base, "text": None, "error": str(exc)}

    extracted = _extract_response_text(response)
    if not extracted:
        return {
            **base,
            "text": None,
            "error": "empty response from model",
        }
    return {**base, "text": extracted}
