"""Public credential endpoints (masked)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.auth.api_key import require_api_key
from app.auth.context import current_auth
from app.db.models import ApiKey
from app.db.session import get_session
from app.schemas_api import CredentialCreate, CredentialListItem, CredentialOut, CredentialUpdate


router = APIRouter(prefix="/credentials", tags=["credentials"])


@router.get("", response_model=list[CredentialListItem])
def list_credentials_v1(
    session: Session = Depends(get_session),
    _auth: ApiKey = Depends(require_api_key),
) -> list[CredentialListItem]:
    from app.routers.credentials import list_credentials_impl

    return list_credentials_impl(session, current_auth().org_id)


@router.post("", response_model=CredentialOut, status_code=201)
def create_credential_v1(
    body: CredentialCreate,
    session: Session = Depends(get_session),
    _auth: ApiKey = Depends(require_api_key),
) -> CredentialOut:
    from app.routers.credentials import create_credential_for_org

    ctx = current_auth()
    return create_credential_for_org(body, session, ctx.org_id, created_by=ctx.user_id)


@router.get("/{credential_id}", response_model=CredentialOut)
def get_credential_v1(
    credential_id: str,
    session: Session = Depends(get_session),
    _auth: ApiKey = Depends(require_api_key),
) -> CredentialOut:
    from app.routers.credentials import get_credential_for_org

    return get_credential_for_org(credential_id, session, current_auth().org_id)


@router.patch("/{credential_id}", response_model=CredentialOut)
def update_credential_v1(
    credential_id: str,
    body: CredentialUpdate,
    session: Session = Depends(get_session),
    _auth: ApiKey = Depends(require_api_key),
) -> CredentialOut:
    from app.routers.credentials import update_credential_for_org

    return update_credential_for_org(
        credential_id, body, session, current_auth().org_id
    )


@router.delete("/{credential_id}")
def delete_credential_v1(
    credential_id: str,
    session: Session = Depends(get_session),
    _auth: ApiKey = Depends(require_api_key),
) -> dict:
    from app.routers.credentials import delete_credential_for_org

    return delete_credential_for_org(credential_id, session, current_auth().org_id)


__all__ = ["router"]
