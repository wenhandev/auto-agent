"""Platform admin authorization dependency."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlmodel import Session

from app.auth.authorization import AuthContext
from app.auth.context import get_org_context
from app.db.models import User
from app.db.session import get_session


async def require_platform_admin(
    ctx: AuthContext = Depends(get_org_context),
    session: Session = Depends(get_session),
) -> User:
    if not ctx.user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    user = session.get(User, ctx.user_id)
    if user is None or user.disabled_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    if not user.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient permissions",
        )
    return user


__all__ = ["require_platform_admin"]
