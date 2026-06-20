"""Route LLM calls from the worker process through the cloud proxy."""

from __future__ import annotations

import base64
import logging
from typing import Any, Optional

import httpx


logger = logging.getLogger(__name__)


class CloudLlmClient:
    """Minimal google.genai.Client stand-in that POSTs to the cloud LLM proxy."""

    def __init__(self, *, cloud_url: str, token: str) -> None:
        self._base = cloud_url.rstrip("/")
        self._token = token

    class _AioModels:
        def __init__(self, outer: CloudLlmClient) -> None:
            self._outer = outer

        async def generate_content(
            self,
            model: str,
            contents: Any,
            config: Any = None,
            **_: Any,
        ) -> Any:
            messages: list[dict[str, Any]] = []
            image_b64: Optional[str] = None
            image_mime = "image/png"
            for item in contents or []:
                role = getattr(item, "role", None) or "user"
                parts = getattr(item, "parts", None) or []
                text_parts: list[str] = []
                for part in parts:
                    text = getattr(part, "text", None)
                    if text:
                        text_parts.append(str(text))
                        continue
                    inline = getattr(part, "inline_data", None)
                    if inline is not None:
                        data = getattr(inline, "data", None)
                        mime = getattr(inline, "mime_type", None) or "image/png"
                        if data:
                            image_b64 = base64.b64encode(data).decode("ascii")
                            image_mime = str(mime)
                if text_parts:
                    messages.append({"role": role, "content": "\n".join(text_parts)})
            system_instruction = getattr(config, "system_instruction", None)
            payload: dict[str, Any] = {
                "purpose": model,
                "messages": messages,
            }
            if system_instruction:
                payload["system_instruction"] = str(system_instruction)
            if image_b64:
                payload["image_b64"] = image_b64
                payload["image_mime"] = image_mime
            async with httpx.AsyncClient(timeout=120.0) as client:
                res = await client.post(
                    f"{self._outer._base}/api/v1/internal/llm/complete",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._outer._token}"},
                )
            res.raise_for_status()
            data = res.json()
            text = str(data.get("text") or "")

            class _Part:
                text = text

            class _Content:
                parts = [_Part()]

            class _Candidate:
                content = _Content()

            class _Response:
                text = text
                candidates = [_Candidate()]

            return _Response()

    @property
    def aio(self) -> _AioModels:
        return self._AioModels(self)

    @property
    def models(self) -> _AioModels:
        return self._AioModels(self)


def install_llm_proxy(*, cloud_url: str, token: str) -> None:
    """Monkeypatch model helpers so worker runs use cloud LLM keys."""
    import app.agents.model as model_mod

    client = CloudLlmClient(cloud_url=cloud_url, token=token)

    def _get_genai_client() -> CloudLlmClient:
        return client

    model_mod.get_genai_client = _get_genai_client  # type: ignore[assignment]
    model_mod.set_llm_client_factory(lambda: "cloud-proxy")


__all__ = ["CloudLlmClient", "install_llm_proxy"]
