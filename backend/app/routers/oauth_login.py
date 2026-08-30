"""Google (and future) OAuth login for platform users."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from app.db.models import User
from app.db.session import get_session
from app.auth.responses import LoginResponse
from app.services.auth_login import build_login_response
from app.services.oauth import providers as oauth_providers
from app.services.oauth.exchange_store import consume_exchange_code, issue_exchange_code
from app.services.oauth.pkce import (
    generate_code_challenge,
    generate_code_verifier,
    generate_state_token,
)
from app.services.oauth.resolver import resolve_oauth_login
from app.services.oauth.state_cookie import (
    OAUTH_STATE_COOKIE,
    OAUTH_STATE_TTL_SECONDS,
    pack_oauth_state_cookie,
    unpack_oauth_state_cookie,
)
from app.settings import settings

router = APIRouter(prefix="/api/auth/oauth", tags=["auth"])


class OAuthExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)


def _oauth_frontend_callback_url(
    *,
    error: str | None = None,
    code: str | None = None,
    client_type: str | None = None,
) -> str:
    params: dict[str, str] = {}
    if error:
        params["error"] = error
    if code:
        params["code"] = code
    query = f"?{urlencode(params)}" if params else ""
    if client_type == "desktop":
        base = settings.desktop_client_base_url.rstrip("/")
    else:
        base = settings.frontend_base_url.rstrip("/")
    return f"{base}/login/oauth/callback{query}"


def _require_provider(provider: str) -> None:
    if provider not in oauth_providers.SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown provider")
    if not oauth_providers.provider_is_configured(settings, provider):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown provider")


def _oauth_cookie_secure() -> bool:
    return settings.frontend_base_url.lower().startswith("https://")


def _client_type_from_request(request: Request) -> str | None:
    cookie_value = request.cookies.get(OAUTH_STATE_COOKIE)
    if not cookie_value:
        return None
    stored = unpack_oauth_state_cookie(cookie_value, secret=settings.session_secret)
    if stored is None:
        return None
    client_type = stored.get("client_type")
    return client_type if client_type in ("desktop",) else None


@router.get("/providers")
def list_oauth_providers() -> dict[str, object]:
    return {
        "providers": settings.enabled_oauth_providers(),
        "password_login_enabled": settings.oauth_password_login_enabled,
    }


@router.get("/{provider}/start")
def oauth_start(provider: str, client: str | None = None) -> RedirectResponse:
    _require_provider(provider)
    client_type = client if client in ("desktop",) else None
    state = generate_state_token()
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    authorize_url = oauth_providers.build_authorize_url(
        provider=provider,
        settings=settings,
        state=state,
        code_challenge=code_challenge,
    )
    response = RedirectResponse(url=authorize_url, status_code=status.HTTP_302_FOUND)
    cookie_value = pack_oauth_state_cookie(
        secret=settings.session_secret,
        provider=provider,
        state=state,
        code_verifier=code_verifier,
        client_type=client_type,
    )
    response.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=cookie_value,
        httponly=True,
        secure=_oauth_cookie_secure(),
        samesite="lax",
        max_age=OAUTH_STATE_TTL_SECONDS,
        path="/api/auth/oauth",
    )
    return response


@router.get("/{provider}/callback")
async def oauth_callback(
    request: Request,
    provider: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: Session = Depends(get_session),
) -> RedirectResponse:
    client_type = _client_type_from_request(request)
    if provider not in oauth_providers.SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown provider")
    if error:
        return RedirectResponse(
            url=_oauth_frontend_callback_url(error=error, client_type=client_type),
            status_code=status.HTTP_302_FOUND,
        )
    if not code or not state:
        return RedirectResponse(
            url=_oauth_frontend_callback_url(error="oauth_failed", client_type=client_type),
            status_code=status.HTTP_302_FOUND,
        )
    cookie_value = request.cookies.get(OAUTH_STATE_COOKIE)
    if not cookie_value:
        return RedirectResponse(
            url=_oauth_frontend_callback_url(error="oauth_failed", client_type=client_type),
            status_code=status.HTTP_302_FOUND,
        )
    stored = unpack_oauth_state_cookie(cookie_value, secret=settings.session_secret)
    if stored is None or stored["provider"] != provider or stored["state"] != state:
        return RedirectResponse(
            url=_oauth_frontend_callback_url(error="oauth_failed", client_type=client_type),
            status_code=status.HTTP_302_FOUND,
        )
    client_type = stored.get("client_type")
    try:
        tokens = await oauth_providers.exchange_code_for_tokens(
            provider=provider,
            settings=settings,
            code=code,
            code_verifier=stored["code_verifier"],
        )
        access_token = tokens.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ValueError("Missing access token")
        profile = await oauth_providers.fetch_user_profile(
            provider=provider,
            access_token=access_token,
        )
        user = resolve_oauth_login(
            session,
            provider=provider,
            subject_id=profile.subject_id,
            email=profile.email,
        )
        session.commit()
        exchange_code = issue_exchange_code(user_id=user.id)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "oauth_failed"
        return RedirectResponse(
            url=_oauth_frontend_callback_url(error=detail, client_type=client_type),
            status_code=status.HTTP_302_FOUND,
        )
    except Exception:
        return RedirectResponse(
            url=_oauth_frontend_callback_url(error="oauth_failed", client_type=client_type),
            status_code=status.HTTP_302_FOUND,
        )
    response = RedirectResponse(
        url=_oauth_frontend_callback_url(code=exchange_code, client_type=client_type),
        status_code=status.HTTP_302_FOUND,
    )
    response.delete_cookie(key=OAUTH_STATE_COOKIE, path="/api/auth/oauth")
    return response


@router.post("/exchange", response_model=LoginResponse)
def oauth_exchange(
    payload: OAuthExchangeRequest,
    response: Response,
    session: Session = Depends(get_session),
) -> LoginResponse:
    user_id = consume_exchange_code(payload.code)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid or expired exchange code",
        )
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid or expired exchange code",
        )
    return build_login_response(session, user, response=response)
