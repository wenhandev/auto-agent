"""API key generation, hashing, and persistence."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

from app.db.models import ApiKey


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def generate_key_material() -> tuple[str, str, str]:
    """Return ``(full_key, key_hash, display_prefix)``."""
    token = secrets.token_urlsafe(32)
    full_key = f"sk_{token}"
    key_hash = hash_key(full_key)
    prefix = f"{full_key[:12]}…"
    return full_key, key_hash, prefix


def count_active_keys(session: Session) -> int:
    rows = session.exec(
        select(ApiKey).where(ApiKey.revoked_at.is_(None))  # type: ignore[union-attr]
    ).all()
    return len(rows)


def create_api_key(
    session: Session,
    *,
    name: str,
    org_id: Optional[str] = None,
) -> tuple[ApiKey, str]:
    from app.services import orgs as org_svc

    resolved_org = org_id or org_svc.get_default_org_id(session)
    full_key, key_hash, prefix = generate_key_material()
    row = ApiKey(
        name=name.strip(),
        key_hash=key_hash,
        prefix=prefix,
        org_id=resolved_org,
        created_at=_utcnow(),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row, full_key


def lookup_by_plaintext(session: Session, plaintext: str) -> Optional[ApiKey]:
    key_hash = hash_key(plaintext)
    return session.exec(
        select(ApiKey).where(
            ApiKey.key_hash == key_hash,
            ApiKey.revoked_at.is_(None),  # type: ignore[union-attr]
        )
    ).first()


def list_api_keys(session: Session, *, org_id: Optional[str] = None) -> list[ApiKey]:
    stmt = (
        select(ApiKey)
        .where(ApiKey.revoked_at.is_(None))  # type: ignore[union-attr]
        .order_by(ApiKey.created_at.desc())  # type: ignore[attr-defined]
    )
    if org_id is not None:
        stmt = stmt.where(ApiKey.org_id == org_id)
    return list(session.exec(stmt).all())


def revoke_api_key(session: Session, key_id: str, *, org_id: Optional[str] = None) -> ApiKey:
    row = session.get(ApiKey, key_id)
    if row is None or row.revoked_at is not None:
        raise ValueError("api key not found")
    if org_id is not None and row.org_id != org_id:
        raise ValueError("api key not found")
    row.revoked_at = _utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def touch_last_used(session: Session, row: ApiKey) -> None:
    row.last_used_at = _utcnow()
    session.add(row)
    session.commit()


__all__ = [
    "hash_key",
    "generate_key_material",
    "count_active_keys",
    "create_api_key",
    "lookup_by_plaintext",
    "list_api_keys",
    "revoke_api_key",
    "touch_last_used",
]
