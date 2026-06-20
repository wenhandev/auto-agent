from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.db.models import OrgMembership, OAuthDomainRule, Organization, User, UserIdentity
from app.services import orgs as org_svc
from app.settings import settings

logger = logging.getLogger(__name__)


def resolve_oauth_login(
    session: Session,
    *,
    provider: str,
    subject_id: str,
    email: str,
) -> User:
    normalized_email = email.strip().lower()
    identity = session.exec(
        select(UserIdentity).where(
            UserIdentity.provider == provider,
            UserIdentity.provider_subject_id == subject_id,
        )
    ).first()
    if identity is not None:
        user = session.get(User, identity.user_id)
        if user is None or user.disabled_at is not None:
            logger.info(
                "oauth_login_rejected reason=identity_orphan provider=%s subject=%s",
                provider,
                subject_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="account_not_provisioned",
            )
        return user

    user = session.exec(select(User).where(User.email == normalized_email)).first()
    if user is not None:
        if user.disabled_at is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="account_not_provisioned",
            )
        session.add(
            UserIdentity(
                user_id=user.id,
                provider=provider,
                provider_subject_id=subject_id,
                email_at_link=normalized_email,
            )
        )
        return user

    if settings.oauth_signup_policy != "domain_allowlist":
        logger.info(
            "oauth_login_rejected reason=existing_users_only email=%s provider=%s",
            normalized_email,
            provider,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="account_not_provisioned",
        )

    domain = normalized_email.rsplit("@", 1)[-1].lower()
    rule = session.exec(
        select(OAuthDomainRule).where(OAuthDomainRule.domain == domain)
    ).first()
    if rule is not None:
        org = session.get(Organization, rule.org_id)
        if org is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="account_not_provisioned",
            )
        user = User(
            email=normalized_email,
            password_hash=None,
            name=normalized_email.split("@")[0],
        )
        session.add(user)
        session.flush()
        session.add(
            OrgMembership(
                user_id=user.id,
                org_id=rule.org_id,
                role=rule.default_role,
            )
        )
        session.add(
            UserIdentity(
                user_id=user.id,
                provider=provider,
                provider_subject_id=subject_id,
                email_at_link=normalized_email,
            )
        )
        return user

    allowed = {
        d.strip().lower()
        for d in (settings.oauth_allowed_email_domains or "").split(",")
        if d.strip()
    }
    if domain not in allowed:
        logger.info(
            "oauth_login_rejected reason=domain_not_allowed email=%s domain=%s",
            normalized_email,
            domain,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="account_not_provisioned",
        )

    org = org_svc.ensure_bootstrap(session)
    user = User(
        email=normalized_email,
        password_hash=None,
        name=normalized_email.split("@")[0],
    )
    session.add(user)
    session.flush()
    session.add(
        OrgMembership(
            user_id=user.id,
            org_id=org.id,
            role=settings.oauth_default_role,
        )
    )
    session.add(
        UserIdentity(
            user_id=user.id,
            provider=provider,
            provider_subject_id=subject_id,
            email_at_link=normalized_email,
        )
    )
    return user
