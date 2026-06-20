"""Dev/test-only reCAPTCHA verification endpoint (no auth required)."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Form, HTTPException

from app.settings import settings


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/test", tags=["test"])

RECAPTCHA_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"


@router.get("/recaptcha-config")
async def recaptcha_config() -> dict[str, str]:
    """Return the configured reCAPTCHA v2 site key for test pages."""
    return {"site_key": settings.recaptcha_site_key}


async def _verify_recaptcha_token(token: str, remote_ip: str | None = None) -> dict[str, Any]:
    payload: dict[str, str] = {
        "secret": settings.recaptcha_secret_key,
        "response": token,
    }
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
            resp = await client.post(RECAPTCHA_VERIFY_URL, data=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("reCAPTCHA siteverify request failed: %s", exc)
        raise HTTPException(status_code=502, detail="reCAPTCHA verification service unavailable") from exc

    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="invalid reCAPTCHA verification response")
    return data


@router.post("/recaptcha-verify")
async def recaptcha_verify(
    g_recaptcha_response: str = Form(..., alias="g-recaptcha-response"),
    password: str = Form(""),
    name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
) -> dict[str, Any]:
    """Verify a reCAPTCHA v2 token with Google siteverify and echo form fields."""
    token = (g_recaptcha_response or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="missing g-recaptcha-response")

    verify_data = await _verify_recaptcha_token(token)
    if not verify_data.get("success"):
        codes = verify_data.get("error-codes") or []
        return {
            "success": False,
            "error": "reCAPTCHA verification failed",
            "error_codes": codes,
        }

    return {
        "success": True,
        "message": "Registration verified",
        "fields": {
            "password": password,
            "name": name,
            "email": email,
            "phone": phone,
        },
        "recaptcha": {
            "hostname": verify_data.get("hostname"),
            "challenge_ts": verify_data.get("challenge_ts"),
        },
    }
