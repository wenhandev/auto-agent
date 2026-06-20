"""Proxy configuration: DB rows, resolution for browser contexts, credential masking."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlmodel import Session

from app.db.crypto import decrypt, encrypt
from app.db.models import BrowserProfile, ProxyConfig, Run
from app.db.session import engine
from app.services.credential_masking import mask_secret
from app.settings import settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def mask_proxy_dict(proxy: dict[str, Any]) -> dict[str, Any]:
    """Return a trace-safe proxy dict with credentials masked."""
    out = dict(proxy)
    if out.get("username"):
        out["username"] = mask_secret(str(out["username"]))
    if out.get("password"):
        out["password"] = mask_secret(str(out["password"]))
    server = str(out.get("server") or "")
    if "@" in server:
        # http://user:pass@host:port -> http://***:***@host:port
        scheme, rest = server.split("://", 1) if "://" in server else ("", server)
        if "@" in rest:
            _, hostpart = rest.rsplit("@", 1)
            out["server"] = f"{scheme}://***:***@{hostpart}" if scheme else f"***:***@{hostpart}"
    return out


def proxy_row_to_playwright(row: ProxyConfig) -> dict[str, str]:
    opts: dict[str, str] = {"server": row.server}
    if row.username:
        opts["username"] = row.username
    if row.password_ciphertext:
        try:
            opts["password"] = decrypt(row.password_ciphertext).decode("utf-8")
        except Exception:
            pass
    return opts


def env_proxy_to_playwright() -> Optional[dict[str, str]]:
    """Global proxy from settings (PROXY_URL + optional auth)."""
    server = settings.proxy_url
    if not server:
        return None
    opts: dict[str, str] = {"server": server}
    if settings.proxy_username:
        opts["username"] = settings.proxy_username
    if settings.proxy_password:
        opts["password"] = settings.proxy_password
    return opts


def load_proxy_by_id(proxy_id: str, session: Optional[Session] = None) -> Optional[dict[str, str]]:
    owns = session is None
    db = session or Session(engine)
    try:
        row = db.get(ProxyConfig, proxy_id)
        if row is None:
            return None
        return proxy_row_to_playwright(row)
    finally:
        if owns:
            db.close()


def resolve_proxy_for_run(
    run_id: str,
    profile_id: Optional[str] = None,
    *,
    session: Optional[Session] = None,
) -> Optional[dict[str, str]]:
    """Resolve proxy: run > profile > default_proxy_id > env PROXY_URL."""
    owns = session is None
    db = session or Session(engine)
    try:
        run = db.get(Run, run_id)
        if run is None and profile_id is None:
            return _fallback_default(db)

        proxy_id: Optional[str] = None
        if run is not None and run.proxy_id:
            proxy_id = run.proxy_id
        elif profile_id:
            profile = db.get(BrowserProfile, profile_id)
            if profile is not None and profile.proxy_id:
                proxy_id = profile.proxy_id
        elif run is not None and run.browser_profile_id:
            profile = db.get(BrowserProfile, run.browser_profile_id)
            if profile is not None and profile.proxy_id:
                proxy_id = profile.proxy_id

        if proxy_id:
            resolved = load_proxy_by_id(proxy_id, session=db)
            if resolved is not None:
                return resolved
        return _fallback_default(db)
    finally:
        if owns:
            db.close()


def _fallback_default(session: Session) -> Optional[dict[str, str]]:
    if settings.default_proxy_id:
        resolved = load_proxy_by_id(settings.default_proxy_id, session=session)
        if resolved is not None:
            return resolved
    return env_proxy_to_playwright()


def create_proxy_row(
    *,
    name: str,
    server: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
    session: Session,
) -> ProxyConfig:
    ciphertext: Optional[bytes] = None
    if password:
        ciphertext = encrypt(password.encode("utf-8"))
    row = ProxyConfig(
        name=name,
        server=server,
        username=username,
        password_ciphertext=ciphertext,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def proxy_row_to_public(row: ProxyConfig) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "server": row.server,
        "username": mask_secret(row.username) if row.username else None,
        "has_password": bool(row.password_ciphertext),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


__all__ = [
    "create_proxy_row",
    "env_proxy_to_playwright",
    "load_proxy_by_id",
    "mask_proxy_dict",
    "proxy_row_to_playwright",
    "proxy_row_to_public",
    "resolve_proxy_for_run",
]
