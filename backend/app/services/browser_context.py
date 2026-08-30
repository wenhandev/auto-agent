"""Resolve merged Playwright context options for a run (profile, proxy, anti-bot)."""

from __future__ import annotations

from typing import Any, Optional

from sqlmodel import Session

from app.db.models import BrowserProfile
from app.db.session import engine
from app.services import antibot as antibot_svc
from app.services import browser_profiles as profile_svc
from app.services import proxy_config as proxy_svc
from app.settings import settings


DEFAULT_VIEWPORT = {
    "width": settings.browser_viewport_width,
    "height": settings.browser_viewport_height,
}


def _safe_get(db: Session, model: type, pk: str) -> Any | None:
    """Worker bundles may ship without cloud SQLite tables."""
    try:
        return db.get(model, pk)
    except Exception:
        return None


def resolve_context_options(
    run_id: str,
    profile_id: Optional[str] = None,
    *,
    session: Optional[Session] = None,
) -> dict[str, Any]:
    owns = session is None
    db = session or Session(engine)
    try:
        profile_opts: dict[str, Any] = {}
        effective_profile_id = profile_id
        if effective_profile_id is None:
            from app.db.models import Run

            run = _safe_get(db, Run, run_id)
            if run is not None and run.browser_profile_id:
                effective_profile_id = run.browser_profile_id

        if effective_profile_id:
            profile = _safe_get(db, BrowserProfile, effective_profile_id)
            if profile is not None:
                profile_opts = profile_svc.build_context_options(profile)
                profile_opts.update(antibot_svc.profile_fingerprint_options(profile))

        proxy = proxy_svc.resolve_proxy_for_run(
            run_id, effective_profile_id, session=db
        )
        proxy_opts: dict[str, Any] = {}
        if proxy:
            proxy_opts["proxy"] = proxy

        global_opts = antibot_svc.global_fingerprint_options()
        merged = antibot_svc.merge_context_options(global_opts, profile_opts, proxy_opts)
        if "viewport" not in merged:
            merged["viewport"] = dict(DEFAULT_VIEWPORT)
        return merged
    finally:
        if owns:
            db.close()


__all__ = ["DEFAULT_VIEWPORT", "resolve_context_options"]
