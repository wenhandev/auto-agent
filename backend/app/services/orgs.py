"""Organisation bootstrap, default-tenant helpers, and backfill."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

import bcrypt
from sqlmodel import Session, select

from app.db.models import (
    ApiKey,
    Credential,
    Organization,
    OrgMembership,
    Run,
    User,
    Workflow,
)
from app.db.session import engine
from app.settings import settings


logger = logging.getLogger(__name__)

DEFAULT_ORG_NAME = "Default Organization"
ORG_ROLES = frozenset({"owner", "admin", "member", "viewer"})

_DEFAULT_ORG_ID: Optional[str] = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(plaintext: str) -> str:
    return bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plaintext: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def get_default_org_id(session: Session) -> str:
    org = session.exec(
        select(Organization).where(Organization.name == DEFAULT_ORG_NAME)
    ).first()
    if org is None:
        org = ensure_bootstrap(session)
    return org.id


def get_default_org_id_from_engine() -> str:
    with Session(engine) as session:
        return get_default_org_id(session)


def resolve_org_id(session: Session, header_org_id: Optional[str]) -> str:
    if header_org_id:
        org = session.get(Organization, header_org_id)
        if org is None:
            raise ValueError(f"organisation {header_org_id!r} not found")
        return org.id
    return get_default_org_id(session)


def lookup_membership_role(
    session: Session, user_id: str, org_id: str
) -> Optional[str]:
    row = session.exec(
        select(OrgMembership).where(
            OrgMembership.user_id == user_id,
            OrgMembership.org_id == org_id,
        )
    ).first()
    if row is None or row.role not in ORG_ROLES:
        return None
    return row.role


def ensure_bootstrap(session: Session) -> Organization:
    """Create default org + admin user if missing. Idempotent."""
    org = session.exec(
        select(Organization).where(Organization.name == DEFAULT_ORG_NAME)
    ).first()
    if org is None:
        org = Organization(name=DEFAULT_ORG_NAME, created_at=_utcnow())
        session.add(org)
        session.flush()
        logger.warning("multi-user bootstrap: created default organisation id=%s", org.id)

    admin_email = (settings.admin_email or "admin@localhost").strip().lower()
    user = session.exec(select(User).where(User.email == admin_email)).first()
    if user is None:
        if settings.bootstrap_oauth_only:
            user = User(
                email=admin_email,
                password_hash=None,
                name="Administrator",
                created_at=_utcnow(),
            )
            session.add(user)
            session.flush()
            logger.warning(
                "multi-user bootstrap: created OAuth-only admin user id=%s",
                user.id,
            )
        else:
            password = settings.admin_password or secrets.token_urlsafe(16)
            if not settings.admin_password:
                logger.warning(
                    "multi-user bootstrap: ADMIN_PASSWORD unset; one-time password for %s: %s",
                    admin_email,
                    password,
                )
            user = User(
                email=admin_email,
                password_hash=hash_password(password),
                name="Administrator",
                created_at=_utcnow(),
            )
            session.add(user)
            session.flush()
            logger.warning("multi-user bootstrap: created admin user id=%s", user.id)

    if settings.bootstrap_platform_admin and not user.is_platform_admin:
        user.is_platform_admin = True
        session.add(user)
        logger.warning(
            "multi-user bootstrap: granted platform admin to user id=%s",
            user.id,
        )

    membership = session.exec(
        select(OrgMembership).where(
            OrgMembership.user_id == user.id,
            OrgMembership.org_id == org.id,
        )
    ).first()
    if membership is None:
        session.add(
            OrgMembership(
                user_id=user.id,
                org_id=org.id,
                role="owner",
                created_at=_utcnow(),
            )
        )

    if settings.bootstrap_platform_admin and not user.is_platform_admin:
        user.is_platform_admin = True
        session.add(user)
        logger.warning(
            "multi-user bootstrap: granted platform admin to user id=%s",
            user.id,
        )

    session.commit()
    session.refresh(org)
    global _DEFAULT_ORG_ID
    _DEFAULT_ORG_ID = org.id
    return org


def backfill_org_ownership(marker_path) -> None:
    """Assign existing rows to the default org (one-shot, marker-guarded)."""
    if marker_path.exists():
        return

    with Session(engine) as session:
        org = ensure_bootstrap(session)
        admin = session.exec(
            select(User).where(User.email == (settings.admin_email or "admin@localhost").strip().lower())
        ).first()
        admin_id = admin.id if admin else None

        for wf in session.exec(select(Workflow).where(Workflow.org_id.is_(None))).all():  # type: ignore[union-attr]
            wf.org_id = org.id
            if admin_id and not wf.created_by:
                wf.created_by = admin_id
            session.add(wf)

        for run in session.exec(select(Run).where(Run.org_id.is_(None))).all():  # type: ignore[union-attr]
            if run.org_id is None:
                wf = session.get(Workflow, run.workflow_id)
                run.org_id = wf.org_id if wf and wf.org_id else org.id
            session.add(run)

        for cred in session.exec(select(Credential).where(Credential.org_id.is_(None))).all():  # type: ignore[union-attr]
            cred.org_id = org.id
            if admin_id and not cred.created_by:
                cred.created_by = admin_id
            session.add(cred)

        for key in session.exec(select(ApiKey)).all():
            if key.org_id is None:
                key.org_id = key.owner_id or org.id
                session.add(key)

        org_id = org.id
        session.commit()

    marker_path.write_text("ok\n", encoding="utf-8")
    logger.warning(
        "org backfill migration: assigned existing resources to default org id=%s",
        org_id,
    )


def scope_orphan_rows_to_default_org() -> None:
    """Assign rows with NULL ``org_id`` to the default org (test/dev helper)."""
    with Session(engine) as session:
        org = ensure_bootstrap(session)
        admin = session.exec(
            select(User).where(
                User.email == (settings.admin_email or "admin@localhost").strip().lower()
            )
        ).first()
        admin_id = admin.id if admin else None

        for wf in session.exec(select(Workflow).where(Workflow.org_id.is_(None))).all():  # type: ignore[union-attr]
            wf.org_id = org.id
            if admin_id and not wf.created_by:
                wf.created_by = admin_id
            session.add(wf)

        for run in session.exec(select(Run).where(Run.org_id.is_(None))).all():  # type: ignore[union-attr]
            wf = session.get(Workflow, run.workflow_id)
            run.org_id = wf.org_id if wf and wf.org_id else org.id
            session.add(run)

        for cred in session.exec(select(Credential).where(Credential.org_id.is_(None))).all():  # type: ignore[union-attr]
            cred.org_id = org.id
            if admin_id and not cred.created_by:
                cred.created_by = admin_id
            session.add(cred)

        for key in session.exec(select(ApiKey).where(ApiKey.org_id.is_(None))).all():  # type: ignore[union-attr]
            key.org_id = key.owner_id or org.id
            session.add(key)

        session.commit()


__all__ = [
    "DEFAULT_ORG_NAME",
    "ORG_ROLES",
    "backfill_org_ownership",
    "ensure_bootstrap",
    "get_default_org_id",
    "get_default_org_id_from_engine",
    "hash_password",
    "lookup_membership_role",
    "resolve_org_id",
    "scope_orphan_rows_to_default_org",
    "verify_password",
]
