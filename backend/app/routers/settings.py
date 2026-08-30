from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter

from app.schemas_api import AntibotSettingsOut, RuntimeSettingsOut
from app.settings import settings


router = APIRouter(prefix="/api/settings", tags=["settings"])


def _mask_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        tail = url[-4:] if len(url) >= 4 else url
        return f"***{tail}"
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    if parsed.username or parsed.password:
        return f"{parsed.scheme}://***@{host}{parsed.path or ''}"
    return f"{parsed.scheme}://{host}{parsed.path or ''}"


@router.get("/runtime", response_model=RuntimeSettingsOut)
def get_runtime_settings() -> RuntimeSettingsOut:
    worker_only = settings.execution_backend == "control_plane_only"
    return RuntimeSettingsOut(
        execution_backend=settings.execution_backend,
        worker_only=worker_only,
    )


@router.get("/antibot", response_model=AntibotSettingsOut)
def get_antibot_settings() -> AntibotSettingsOut:
    proxy_url = settings.proxy_url
    return AntibotSettingsOut(
        source="env",
        editable=False,
        captcha_detection_enabled=bool(settings.captcha_detection_enabled),
        captcha_builtin_heuristics_enabled=bool(
            settings.captcha_builtin_heuristics_enabled
        ),
        captcha_solver=settings.captcha_solver or "manual",
        captcha_external_solver_url_masked=_mask_url(settings.captcha_external_solver_url),
        captcha_external_solver_key_configured=bool(settings.captcha_external_solver_key),
        antibot_stealth=bool(settings.antibot_stealth),
        antibot_user_agent=settings.antibot_user_agent,
        antibot_locale=settings.antibot_locale,
        antibot_timezone_id=settings.antibot_timezone_id,
        antibot_viewport_width=settings.antibot_viewport_width,
        antibot_viewport_height=settings.antibot_viewport_height,
        default_proxy_id=settings.default_proxy_id,
        proxy_configured=bool(proxy_url),
        proxy_url_masked=_mask_url(proxy_url),
        proxy_username_configured=bool(settings.proxy_username),
        proxy_password_configured=bool(settings.proxy_password),
    )


__all__ = ["router"]
