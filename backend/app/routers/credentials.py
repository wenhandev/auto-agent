from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.auth.context import AuthContext, get_org_context, org_scope_filter, require_org_match

from sqlalchemy import func

from app.db.crypto import decrypt, encrypt
from app.db.models import Credential, WorkflowCredential
from app.db.session import get_session
from app.integrations.credential_types import get_credential_type, list_credential_types
from app.integrations.registry import get_registry
from app.schemas_api import (
    CredentialCreate,
    CredentialFieldMasked,
    CredentialListItem,
    CredentialOut,
    CredentialTypeAuthOut,
    CredentialTypeFieldOut,
    CredentialTypeOut,
    CredentialUpdate,
)
from app.services.credential_masking import mask_field


router = APIRouter(prefix="/api/credentials", tags=["credentials"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _mask(value: str, *, field_name: str = "", credential_type: str = "generic") -> str:
    return mask_field(field_name, value, credential_type=credential_type)


def _decrypt_fields(cred: Credential) -> dict[str, str]:
    try:
        plain = decrypt(cred.ciphertext)
    except Exception as exc:
        raise HTTPException(
            500, detail="credential vault: decryption failed; secret key may have changed"
        ) from exc
    try:
        data = json.loads(plain.decode("utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def _to_out(cred: Credential) -> CredentialOut:
    fields = _decrypt_fields(cred)
    ctype = cred.type or "generic"
    return CredentialOut(
        id=cred.id,
        name=cred.name,
        type=ctype,
        description=cred.description,
        fields=[
            CredentialFieldMasked(
                name=k,
                masked_value=_mask(v, field_name=k, credential_type=ctype),
            )
            for k, v in fields.items()
        ],
        created_at=cred.created_at,
        updated_at=cred.updated_at,
    )


def _to_list_item(cred: Credential, usage_count: int = 0) -> CredentialListItem:
    fields = _decrypt_fields(cred)
    return CredentialListItem(
        id=cred.id,
        name=cred.name,
        type=cred.type or "generic",
        description=cred.description,
        field_names=list(fields.keys()),
        updated_at=cred.updated_at,
        usage_count=usage_count,
    )


def _usage_counts(session: Session) -> dict[str, int]:
    rows = session.exec(
        select(
            WorkflowCredential.credential_id,
            func.count(WorkflowCredential.id),
        ).group_by(WorkflowCredential.credential_id)
    ).all()
    return {cid: count for cid, count in rows}


def list_credentials_impl(session: Session, org_id: str) -> list[CredentialListItem]:
    rows = session.exec(
        select(Credential)
        .where(org_scope_filter(Credential, org_id, session))
        .order_by(Credential.updated_at.desc())  # type: ignore[attr-defined]
    ).all()
    counts = _usage_counts(session)
    return [_to_list_item(c, counts.get(c.id, 0)) for c in rows]


def _oauth_connect_app(cred_type: str) -> str | None:
    for app, desc in get_registry().items():
        if cred_type in desc.credentials:
            ct = get_credential_type(cred_type)
            if ct is not None and ct.auth.strategy == "oauth2":
                return app
    return None


def _to_credential_type_out(ct) -> CredentialTypeOut:
    connect_app = None
    if ct.auth.strategy == "oauth2":
        connect_app = _oauth_connect_app(ct.type)
    return CredentialTypeOut(
        type=ct.type,
        label=ct.label or ct.type,
        fields=[
            CredentialTypeFieldOut(
                name=f.name,
                label=f.label or f.name,
                kind=f.kind,
                required=f.required,
                default=f.default,
            )
            for f in ct.fields
        ],
        auth=CredentialTypeAuthOut(
            strategy=ct.auth.strategy,
            connect_app=connect_app,
        ),
    )


@router.get("/types", response_model=list[CredentialTypeOut])
def list_credential_type_schemas(
    _ctx: AuthContext = Depends(get_org_context),
) -> list[CredentialTypeOut]:
    from app.integrations.bootstrap import bootstrap_integrations

    bootstrap_integrations()
    types = sorted(list_credential_types(), key=lambda t: t.type)
    return [_to_credential_type_out(ct) for ct in types]


@router.get("", response_model=list[CredentialListItem])
def list_credentials(
    session: Session = Depends(get_session),
    _ctx: AuthContext = Depends(get_org_context),
) -> list[CredentialListItem]:
    return list_credentials_impl(session, _ctx.org_id)


def create_credential_for_org(
    body: CredentialCreate,
    session: Session,
    org_id: str,
    *,
    created_by: str | None = None,
) -> CredentialOut:
    existing = session.exec(
        select(Credential).where(
            Credential.name == body.name,
            Credential.org_id == org_id,
        )
    ).first()
    if existing is not None:
        raise HTTPException(409, detail="credential name already exists")
    cred_type = body.type or "generic"
    if get_credential_type(cred_type) is None:
        raise HTTPException(400, detail=f"unknown credential type {cred_type!r}")
    blob = encrypt(json.dumps(body.fields, ensure_ascii=False).encode("utf-8"))
    cred = Credential(
        name=body.name,
        type=cred_type,
        description=body.description,
        org_id=org_id,
        created_by=created_by,
        ciphertext=blob,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    session.add(cred)
    session.commit()
    session.refresh(cred)
    return _to_out(cred)


@router.post("", response_model=CredentialOut)
def create_credential(
    body: CredentialCreate,
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> CredentialOut:
    return create_credential_for_org(
        body, session, ctx.org_id, created_by=ctx.user_id
    )


def get_credential_for_org(
    credential_id: str, session: Session, org_id: str
) -> CredentialOut:
    cred = session.get(Credential, credential_id)
    if cred is None:
        raise HTTPException(404, detail="credential not found")
    require_org_match(cred.org_id, org_id, session)
    return _to_out(cred)


@router.get("/{credential_id}", response_model=CredentialOut)
def get_credential(
    credential_id: str,
    session: Session = Depends(get_session),
    _ctx: AuthContext = Depends(get_org_context),
) -> CredentialOut:
    return get_credential_for_org(credential_id, session, _ctx.org_id)


def update_credential_for_org(
    credential_id: str,
    body: CredentialUpdate,
    session: Session,
    org_id: str,
) -> CredentialOut:
    cred = session.get(Credential, credential_id)
    if cred is None:
        raise HTTPException(404, detail="credential not found")
    require_org_match(cred.org_id, org_id, session)
    if body.name is not None and body.name != cred.name:
        clash = session.exec(
            select(Credential).where(
                Credential.name == body.name,
                Credential.org_id == org_id,
            )
        ).first()
        if clash is not None:
            raise HTTPException(409, detail="credential name already exists")
        cred.name = body.name
    if body.description is not None:
        cred.description = body.description
    if body.type is not None:
        if get_credential_type(body.type) is None:
            raise HTTPException(400, detail=f"unknown credential type {body.type!r}")
        cred.type = body.type
    if body.fields is not None:
        current = _decrypt_fields(cred)
        current.update(body.fields)
        cred.ciphertext = encrypt(
            json.dumps(current, ensure_ascii=False).encode("utf-8")
        )
    cred.updated_at = _utcnow()
    session.add(cred)
    session.commit()
    session.refresh(cred)
    return _to_out(cred)


@router.patch("/{credential_id}", response_model=CredentialOut)
@router.put("/{credential_id}", response_model=CredentialOut)
def update_credential(
    credential_id: str,
    body: CredentialUpdate,
    session: Session = Depends(get_session),
    _ctx: AuthContext = Depends(get_org_context),
) -> CredentialOut:
    return update_credential_for_org(credential_id, body, session, _ctx.org_id)


def delete_credential_for_org(
    credential_id: str, session: Session, org_id: str
) -> dict:
    cred = session.get(Credential, credential_id)
    if cred is None:
        raise HTTPException(404, detail="credential not found")
    require_org_match(cred.org_id, org_id, session)
    links = session.exec(
        select(WorkflowCredential).where(
            WorkflowCredential.credential_id == credential_id
        )
    ).all()
    for link in links:
        session.delete(link)
    session.delete(cred)
    session.commit()
    return {"ok": True}


@router.delete("/{credential_id}")
def delete_credential(
    credential_id: str,
    session: Session = Depends(get_session),
    _ctx: AuthContext = Depends(get_org_context),
) -> dict:
    return delete_credential_for_org(credential_id, session, _ctx.org_id)


__all__ = ["router"]
