from __future__ import annotations

from functools import cached_property
from typing import Any, Optional, Union

from google.adk.models.google_llm import Gemini
from google.adk.models.lite_llm import LiteLlm
from google.genai import Client, types

from app.settings import settings


class _RelayGemini(Gemini):
    """ADK Gemini variant that injects an explicit api_key and base_url into
    the underlying ``google.genai.Client``.

    Required when targeting an internal relay (e.g. Bosch) that speaks the
    Google-native Gemini protocol but expects the relay's own gateway key
    rather than a Google AI Studio key picked up from the environment.
    """

    api_key: Optional[str] = None

    @cached_property
    def api_client(self) -> Client:
        base_url, api_version = self._base_url_and_api_version
        http_options_kwargs: dict[str, Any] = {
            "headers": self._tracking_headers(),
            "retry_options": self.retry_options,
            "base_url": base_url,
            # `trust_env=False` keeps httpx from inheriting corporate
            # proxy env vars (HTTP_PROXY / NO_PROXY). Bosch's NO_PROXY
            # ships wildcard patterns httpx refuses to parse, and the
            # internal relay is reachable directly anyway.
            "client_args": {"trust_env": False},
            "async_client_args": {"trust_env": False},
        }
        if api_version:
            http_options_kwargs["api_version"] = api_version

        kwargs: dict[str, Any] = {
            "http_options": types.HttpOptions(**http_options_kwargs),
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.model.startswith("projects/"):
            kwargs["vertexai"] = True

        return Client(**kwargs)


def get_adk_model() -> Union[str, Gemini, LiteLlm]:
    from app.services.llm_runtime import get_active_model

    return get_active_model()


def get_genai_client() -> Client:
    """Build a `google.genai.Client` configured for the active provider.

    Mirrors the wiring in `_RelayGemini` so one-shot LLM calls (e.g. the
    extractor) hit the same Bosch relay (or Google AI Studio) and reuse the
    same proxy-bypass behaviour.
    """
    provider = (settings.llm_provider or "openai").lower()
    if provider not in ("google", "gemini"):
        raise RuntimeError(
            f"get_genai_client(): provider {settings.llm_provider!r} is not "
            "google/gemini; the helper currently supports only Gemini-native "
            "calls."
        )
    if not settings.google_api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY is not configured; cannot build genai.Client."
        )

    http_options_kwargs: dict[str, Any] = {
        "client_args": {"trust_env": False},
        "async_client_args": {"trust_env": False},
    }
    if settings.google_base_url:
        http_options_kwargs["base_url"] = settings.google_base_url

    return Client(
        api_key=settings.google_api_key,
        http_options=types.HttpOptions(**http_options_kwargs),
    )


def get_genai_model_id() -> str:
    return settings.google_model
