from __future__ import annotations

import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.db.crypto import decrypt, encrypt
from app.db.models import Credential
from app.db.session import get_session
from app.integrations.credential_types import get_credential_type
from app.integrations.registry import get_descriptor
from app.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/oauth2", tags=["oauth2"])

_STATE_TTL_SEC = 600
_KEY_FILE = Path(__file__).resolve().parents[2] / ".secret_key"


class OAuth2NotConfiguredError(HTTPException):
    def __init__(self, detail: str = "OAuth2 is not configured for this app"):
        super().__init__(status_code=503, detail=detail)


def _state_secret() -> bytes:
    env = os.environ.get("AUTO_AGENT_SECRET_KEY")
    if env:
        return env.encode("utf-8")
    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes()
    return b"auto-agent-oauth-state-dev"


def _sign_state(payload: dict[str, Any]) -> str:
    import base64
    import hashlib
    import hmac

    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(_state_secret(), raw, hashlib.sha256).hexdigest()
    blob = base64.urlsafe_b64encode(
        json.dumps({"p": payload, "s": sig}).encode("utf-8")
    ).decode("ascii")
    return blob


def _verify_state(token: str) -> dict[str, Any]:
    import base64
    import hashlib
    import hmac

    try:
        decoded = json.loads(base64.urlsafe_b64decode(token.encode("ascii")))
        payload = decoded["p"]
        sig = decoded["s"]
    except Exception as exc:
        raise HTTPException(400, detail="invalid oauth state") from exc
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    expected = hmac.new(_state_secret(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(400, detail="invalid oauth state signature")
    issued = float(payload.get("ts", 0))
    if time.time() - issued > _STATE_TTL_SEC:
        raise HTTPException(400, detail="oauth state expired")
    return payload


def _load_cred_fields(cred: Credential) -> dict[str, str]:
    plain = decrypt(cred.ciphertext)
    data = json.loads(plain.decode("utf-8"))
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def _store_cred_fields(cred: Credential, fields: dict[str, str], session: Session) -> None:
    from datetime import datetime, timezone

    cred.ciphertext = encrypt(json.dumps(fields, ensure_ascii=False).encode("utf-8"))
    cred.updated_at = datetime.now(timezone.utc)
    session.add(cred)
    session.commit()


@router.get("/{app}/connect")
def oauth_connect(
    app: str,
    credential_id: str = Query(...),
    session: Session = Depends(get_session),
):
    """Start OAuth2 authorization-code flow. Redirects to provider authorize URL."""
    try:
        desc = get_descriptor(app)
    except KeyError as exc:
        raise HTTPException(404, detail=str(exc)) from exc

    if not desc.credentials:
        raise OAuth2NotConfiguredError("app has no credential types")

    cred = session.get(Credential, credential_id)
    if cred is None:
        raise HTTPException(404, detail="credential not found")

    cred_type = get_credential_type(cred.type or "generic")
    if cred_type is None or cred_type.auth.strategy != "oauth2":
        raise OAuth2NotConfiguredError("credential is not an oauth2 type")

    auth = cred_type.auth
    if not auth.authorize_url or not auth.token_url:
        raise OAuth2NotConfiguredError("oauth2 authorize_url/token_url not configured")

    fields = _load_cred_fields(cred)
    client_id = fields.get(auth.client_id_field or "client_id", "")
    if not client_id:
        raise HTTPException(400, detail="client_id missing on credential")

    state = _sign_state(
        {
            "app": app,
            "credential_id": credential_id,
            "ts": time.time(),
            "nonce": secrets.token_urlsafe(16),
        }
    )
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": f"{settings.oauth_callback_base}/api/oauth2/callback",
        "state": state,
    }
    if auth.scopes:
        params["scope"] = " ".join(auth.scopes)
    url = f"{auth.authorize_url}?{urlencode(params)}"
    return RedirectResponse(url, status_code=302)


async def exchange_authorization_code(
    *,
    token_url: str,
    data: dict[str, str],
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    timeout = httpx.Timeout(15.0)
    async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
        resp = await client.post(token_url, data=data)
    if resp.status_code >= 400:
        raise HTTPException(502, detail=f"token exchange failed: HTTP {resp.status_code}")
    body = resp.json()
    if not isinstance(body, dict):
        raise HTTPException(502, detail="token exchange returned non-object JSON")
    return body


def _oauth_frontend_redirect(
    *,
    connected: bool = False,
    app: str = "",
    credential_id: str = "",
    error: str = "",
) -> RedirectResponse:
    params: dict[str, str] = {}
    if connected:
        params["connected"] = "1"
        if app:
            params["app"] = app
        if credential_id:
            params["credential_id"] = credential_id
    elif error:
        params["error"] = error
    base = settings.frontend_base_url.rstrip("/")
    qs = f"?{urlencode(params)}" if params else ""
    return RedirectResponse(f"{base}/credentials/oauth/callback{qs}", status_code=302)


@router.get("/callback")
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    session: Session = Depends(get_session),
):
    try:
        payload = _verify_state(state)
    except HTTPException as exc:
        detail = str(exc.detail) if isinstance(exc.detail, str) else "oauth_failed"
        return _oauth_frontend_redirect(error=detail)

    app = str(payload["app"])
    credential_id = str(payload["credential_id"])

    cred = session.get(Credential, credential_id)
    if cred is None:
        return _oauth_frontend_redirect(error="credential_not_found")

    cred_type = get_credential_type(cred.type or "generic")
    if cred_type is None or cred_type.auth.strategy != "oauth2":
        return _oauth_frontend_redirect(error="not_oauth2_credential")

    auth = cred_type.auth
    if not auth.token_url:
        return _oauth_frontend_redirect(error="oauth_not_configured")

    fields = _load_cred_fields(cred)
    client_id = fields.get(auth.client_id_field or "client_id", "")
    client_secret = fields.get(auth.client_secret_field or "client_secret", "")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": f"{settings.oauth_callback_base}/api/oauth2/callback",
    }

    try:
        body = await exchange_authorization_code(
            token_url=auth.token_url,
            data=data,
        )
    except HTTPException as exc:
        detail = str(exc.detail) if isinstance(exc.detail, str) else "token_exchange_failed"
        return _oauth_frontend_redirect(error=detail)

    token_field = auth.token_field or "access_token"
    access = str(body.get(token_field, ""))
    if not access:
        return _oauth_frontend_redirect(error="missing_access_token")

    fields[token_field] = access
    if body.get("refresh_token"):
        fields["refresh_token"] = str(body["refresh_token"])
    expires_in = body.get("expires_in")
    if expires_in is not None:
        fields["expires_at"] = str(time.time() + float(expires_in))

    _store_cred_fields(cred, fields, session)
    return _oauth_frontend_redirect(
        connected=True,
        app=app,
        credential_id=credential_id,
    )


__all__ = ["router", "OAuth2NotConfiguredError"]
