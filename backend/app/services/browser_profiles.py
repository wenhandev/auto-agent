from __future__ import annotations

import json
import logging
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from playwright.async_api import BrowserContext
from sqlmodel import Session

from app.db.crypto import decrypt, encrypt
from app.db.models import BrowserProfile
from app.db.session import engine


logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_ROOT = _BACKEND_ROOT / "data" / "profiles"
_profiles_root: Path = _DEFAULT_ROOT


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def set_profiles_root(path: Path) -> None:
    global _profiles_root
    _profiles_root = path


def reset_profiles_root() -> None:
    global _profiles_root
    _profiles_root = _DEFAULT_ROOT


def profiles_root() -> Path:
    return _profiles_root


def ensure_profiles_root() -> Path:
    _profiles_root.mkdir(parents=True, exist_ok=True)
    return _profiles_root


def profile_dir(profile_id: str) -> Path:
    return _profiles_root / profile_id


def storage_state_file(profile_id: str) -> Path:
    return profile_dir(profile_id) / "storage_state.enc"


def _restrict_perms(path: Path) -> None:
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError as exc:
        logger.warning("could not chmod %s to 0600: %s", path, exc)


def _empty_storage_state() -> dict[str, Any]:
    return {"cookies": [], "origins": []}


def _relative_storage_path(profile_id: str) -> str:
    return f"{profile_id}/storage_state.enc"


def write_storage_state(profile_id: str, state: dict[str, Any]) -> str:
    """Encrypt and persist storage_state; return relative path for the DB row."""
    ensure_profiles_root()
    profile_dir(profile_id).mkdir(parents=True, exist_ok=True)
    plain = json.dumps(state, ensure_ascii=False).encode("utf-8")
    path = storage_state_file(profile_id)
    path.write_bytes(encrypt(plain))
    _restrict_perms(path)
    return _relative_storage_path(profile_id)


def read_storage_state(profile_id: str) -> dict[str, Any]:
    path = storage_state_file(profile_id)
    if not path.is_file():
        return _empty_storage_state()
    try:
        plain = decrypt(path.read_bytes())
        data = json.loads(plain.decode("utf-8"))
    except Exception as exc:
        logger.warning("profile %s storage_state decrypt failed: %s", profile_id, exc)
        return _empty_storage_state()
    if not isinstance(data, dict):
        return _empty_storage_state()
    return data


def has_storage_state(profile_id: str) -> bool:
    path = storage_state_file(profile_id)
    if not path.is_file():
        return False
    state = read_storage_state(profile_id)
    return bool(state.get("cookies") or state.get("origins"))


def parse_viewport(profile: BrowserProfile) -> Optional[dict[str, int]]:
    if not profile.viewport_json:
        return None
    try:
        data = json.loads(profile.viewport_json)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    width = data.get("width")
    height = data.get("height")
    if width is None or height is None:
        return None
    return {"width": int(width), "height": int(height)}


def build_context_options(profile: BrowserProfile) -> dict[str, Any]:
    opts: dict[str, Any] = {}
    state = read_storage_state(profile.id)
    if state.get("cookies") or state.get("origins"):
        opts["storage_state"] = state
    if profile.user_agent:
        opts["user_agent"] = profile.user_agent
    if profile.locale:
        opts["locale"] = profile.locale
    if profile.timezone_id:
        opts["timezone_id"] = profile.timezone_id
    viewport = parse_viewport(profile)
    if viewport is not None:
        opts["viewport"] = viewport
    return opts


def load_context_options(profile_id: str, session: Optional[Session] = None) -> dict[str, Any]:
    if session is not None:
        profile = session.get(BrowserProfile, profile_id)
    else:
        with Session(engine) as db:
            profile = db.get(BrowserProfile, profile_id)
    if profile is None:
        raise ValueError(f"browser profile {profile_id!r} not found")
    return build_context_options(profile)


def _filter_state_for_persist(
    profile: BrowserProfile, state: dict[str, Any]
) -> dict[str, Any]:
    cookies = state.get("cookies") or []
    origins = state.get("origins") or []
    if profile.persist_cookies and profile.persist_local_storage:
        return {"cookies": cookies, "origins": origins}
    if profile.persist_cookies:
        return {"cookies": cookies, "origins": []}
    if profile.persist_local_storage:
        return {"cookies": [], "origins": origins}
    return _empty_storage_state()


async def save_from_context(
    profile_id: str,
    context: BrowserContext,
    *,
    session: Optional[Session] = None,
) -> None:
    owns_session = session is None
    db = session or Session(engine)
    try:
        profile = db.get(BrowserProfile, profile_id)
        if profile is None:
            return
        if not profile.persist_cookies and not profile.persist_local_storage:
            return
        raw_state = await context.storage_state()
        filtered = _filter_state_for_persist(profile, raw_state)
        rel_path = write_storage_state(profile_id, filtered)
        profile.storage_state_path = rel_path
        profile.last_used_at = _utcnow()
        profile.updated_at = _utcnow()
        db.add(profile)
        db.commit()
    finally:
        if owns_session:
            db.close()


def create_profile_row(
    *,
    name: str,
    user_agent: Optional[str] = None,
    viewport: Optional[dict[str, int]] = None,
    persist_cookies: bool = True,
    persist_local_storage: bool = True,
    session: Session,
) -> BrowserProfile:
    viewport_json: Optional[str] = None
    if viewport is not None:
        viewport_json = json.dumps(viewport, ensure_ascii=False)
    profile = BrowserProfile(
        name=name,
        user_agent=user_agent,
        viewport_json=viewport_json,
        persist_cookies=persist_cookies,
        persist_local_storage=persist_local_storage,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)
    rel_path = write_storage_state(profile.id, _empty_storage_state())
    profile.storage_state_path = rel_path
    profile.updated_at = _utcnow()
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


def delete_profile_files(profile_id: str) -> None:
    d = profile_dir(profile_id)
    if d.is_dir():
        for child in d.iterdir():
            child.unlink(missing_ok=True)
        d.rmdir()


__all__ = [
    "build_context_options",
    "create_profile_row",
    "delete_profile_files",
    "ensure_profiles_root",
    "has_storage_state",
    "load_context_options",
    "parse_viewport",
    "profiles_root",
    "read_storage_state",
    "reset_profiles_root",
    "save_from_context",
    "set_profiles_root",
    "storage_state_file",
    "write_storage_state",
]
