"""Public API key management."""

from __future__ import annotations

from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.auth.authorization import AuthContext, require_min_role
from app.auth.context import current_auth
from app.auth.deps import require_v1_auth, require_v1_auth_or_bootstrap
from app.db.models import ApiKey
from app.db.session import get_session
from app.schemas_api import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from app.services import api_keys as api_key_svc


router = APIRouter(prefix="/keys", tags=["api-keys"])


def _to_out(row: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(
        id=row.id,
        name=row.name,
        prefix=row.prefix,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
    )


@router.post("", response_model=ApiKeyCreated, status_code=201)
def create_key(
    body: ApiKeyCreate,
    session: Session = Depends(get_session),
    auth: Optional[Union[ApiKey, AuthContext]] = Depends(require_v1_auth_or_bootstrap),
) -> ApiKeyCreated:
    from app.services import orgs as org_svc

    if auth is not None:
        require_min_role(current_auth(), "admin")
    org_id = (
        (auth.org_id if isinstance(auth, AuthContext) else auth.org_id or org_svc.get_default_org_id(session))
        if auth is not None
        else org_svc.get_default_org_id(session)
    )
    row, full_key = api_key_svc.create_api_key(session, name=body.name, org_id=org_id)
    return ApiKeyCreated(
        id=row.id,
        name=row.name,
        prefix=row.prefix,
        key=full_key,
        created_at=row.created_at,
    )


@router.get("", response_model=list[ApiKeyOut])
def list_keys(
    session: Session = Depends(get_session),
    _auth: Union[ApiKey, AuthContext] = Depends(require_v1_auth),
) -> list[ApiKeyOut]:
    return [_to_out(row) for row in api_key_svc.list_api_keys(session, org_id=current_auth().org_id)]


@router.delete("/{key_id}", status_code=204)
def revoke_key(
    key_id: str,
    session: Session = Depends(get_session),
    _auth: Union[ApiKey, AuthContext] = Depends(require_v1_auth),
) -> None:
    require_min_role(current_auth(), "admin")
    try:
        api_key_svc.revoke_api_key(session, key_id, org_id=current_auth().org_id)
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc)) from exc


__all__ = ["router"]
