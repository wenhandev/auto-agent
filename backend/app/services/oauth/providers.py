from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from app.settings import Settings

SUPPORTED_PROVIDERS = frozenset({"google"})


@dataclass(frozen=True)
class OAuthProfile:
    subject_id: str
    email: str


def provider_is_configured(settings: Settings, provider: str) -> bool:
    return provider in settings.enabled_oauth_providers()


def callback_url(settings: Settings, provider: str) -> str:
    base = settings.oauth_callback_base.rstrip("/")
    return f"{base}/api/auth/oauth/{provider}/callback"


def build_authorize_url(
    *,
    provider: str,
    settings: Settings,
    state: str,
    code_challenge: str,
) -> str:
    redirect_uri = callback_url(settings, provider)
    if provider == "google":
        params = {
            "client_id": settings.oauth_google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "online",
            "prompt": "select_account",
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    raise ValueError(f"Unsupported OAuth provider: {provider}")


async def exchange_code_for_tokens(
    *,
    provider: str,
    settings: Settings,
    code: str,
    code_verifier: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    redirect_uri = callback_url(settings, provider)
    async with httpx.AsyncClient(transport=transport) as client:
        if provider == "google":
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": settings.oauth_google_client_id,
                    "client_secret": settings.oauth_google_client_secret,
                    "code": code,
                    "code_verifier": code_verifier or "",
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
        else:
            raise ValueError(f"Unsupported OAuth provider: {provider}")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Invalid token response")
        return payload


async def fetch_user_profile(
    *,
    provider: str,
    access_token: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> OAuthProfile:
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    async with httpx.AsyncClient(transport=transport) as client:
        if provider == "google":
            response = await client.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
            subject = payload.get("sub")
            email = payload.get("email")
            if not isinstance(subject, str) or not isinstance(email, str) or not email:
                raise ValueError("Google profile missing subject or email")
            return OAuthProfile(
                subject_id=subject,
                email=email.strip().lower(),
            )
    raise ValueError(f"Unsupported OAuth provider: {provider}")
