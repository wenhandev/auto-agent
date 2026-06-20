from __future__ import annotations

import subprocess
from functools import cached_property
from typing import Any, Optional, Union

from google.adk.models.google_llm import Gemini
from google.adk.models.lite_llm import LiteLlm
from google.genai import Client, types

from app.settings import llm_is_configured, settings


def _vertex_credentials():
    """Vertex credentials: ADC first, then gcloud (same as voice2navigation)."""
    import google.auth
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    try:
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        creds.refresh(Request())
        if creds.token:
            return creds
    except Exception:
        pass

    token = subprocess.check_output(
        ["gcloud", "auth", "print-access-token"],
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()
    return Credentials(token=token)


class _VertexGemini(Gemini):
    """ADK Gemini wired to Vertex AI with gcloud/ADC credentials."""

    @cached_property
    def api_client(self) -> Client:
        return Client(
            vertexai=True,
            project=settings.gcp_project,
            location=settings.gcp_location,
            credentials=_vertex_credentials(),
            http_options=types.HttpOptions(
                headers=self._tracking_headers(),
                retry_options=self.retry_options,
                client_args={"trust_env": False},
                async_client_args={"trust_env": False},
            ),
        )


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

    override = globals().get("_llm_client_factory")
    if override is not None:
        return override()
    return get_active_model()


def set_llm_client_factory(factory: Optional[Any]) -> None:
    """Override LLM model resolution (used by local worker runtime)."""
    globals()["_llm_client_factory"] = factory


def clear_llm_client_factory() -> None:
    globals()["_llm_client_factory"] = None


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
    if not llm_is_configured():
        raise RuntimeError(
            "GOOGLE_API_KEY / Vertex GCP_PROJECT is not configured; "
            "cannot build genai.Client."
        )

    http_options_kwargs: dict[str, Any] = {
        "client_args": {"trust_env": False},
        "async_client_args": {"trust_env": False},
    }
    if settings.google_base_url:
        http_options_kwargs["base_url"] = settings.google_base_url

    client_kwargs: dict[str, Any] = {
        "http_options": types.HttpOptions(**http_options_kwargs),
    }
    if settings.gemini_provider.lower() == "vertex" and settings.gcp_project:
        client_kwargs["vertexai"] = True
        client_kwargs["project"] = settings.gcp_project
        client_kwargs["location"] = settings.gcp_location
        client_kwargs["credentials"] = _vertex_credentials()
    else:
        client_kwargs["api_key"] = settings.google_api_key

    return Client(**client_kwargs)


def get_genai_model_id() -> str:
    return settings.google_model
