from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from sqlalchemy import func

from app.db.crypto import decrypt, encrypt
from app.db.models import Credential, WorkflowCredential
from app.db.session import get_session
from app.schemas_api import (
    CredentialCreate,
    CredentialFieldMasked,
    CredentialListItem,
    CredentialOut,
    CredentialUpdate,
)


router = APIRouter(prefix="/api/credentials", tags=["credentials"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _mask(value: str) -> str:
    if not value:
        return "***"
    tail = value[-2:] if len(value) >= 2 else value
    return f"***{tail}"


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
    return CredentialOut(
        id=cred.id,
        name=cred.name,
        description=cred.description,
        fields=[
            CredentialFieldMasked(name=k, masked_value=_mask(v))
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


@router.get("", response_model=list[CredentialListItem])
def list_credentials(
    session: Session = Depends(get_session),
) -> list[CredentialListItem]:
    rows = session.exec(
        select(Credential).order_by(Credential.updated_at.desc())  # type: ignore[attr-defined]
    ).all()
    counts = _usage_counts(session)
    return [_to_list_item(c, counts.get(c.id, 0)) for c in rows]


@router.post("", response_model=CredentialOut)
def create_credential(
    body: CredentialCreate, session: Session = Depends(get_session)
) -> CredentialOut:
    existing = session.exec(
        select(Credential).where(Credential.name == body.name)
    ).first()
    if existing is not None:
        raise HTTPException(409, detail="credential name already exists")
    blob = encrypt(json.dumps(body.fields, ensure_ascii=False).encode("utf-8"))
    cred = Credential(
        name=body.name,
        description=body.description,
        ciphertext=blob,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    session.add(cred)
    session.commit()
    session.refresh(cred)
    return _to_out(cred)


@router.get("/{credential_id}", response_model=CredentialOut)
def get_credential(
    credential_id: str, session: Session = Depends(get_session)
) -> CredentialOut:
    cred = session.get(Credential, credential_id)
    if cred is None:
        raise HTTPException(404, detail="credential not found")
    return _to_out(cred)


@router.patch("/{credential_id}", response_model=CredentialOut)
@router.put("/{credential_id}", response_model=CredentialOut)
def update_credential(
    credential_id: str,
    body: CredentialUpdate,
    session: Session = Depends(get_session),
) -> CredentialOut:
    cred = session.get(Credential, credential_id)
    if cred is None:
        raise HTTPException(404, detail="credential not found")
    if body.name is not None and body.name != cred.name:
        clash = session.exec(
            select(Credential).where(Credential.name == body.name)
        ).first()
        if clash is not None:
            raise HTTPException(409, detail="credential name already exists")
        cred.name = body.name
    if body.description is not None:
        cred.description = body.description
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


@router.delete("/{credential_id}")
def delete_credential(
    credential_id: str, session: Session = Depends(get_session)
) -> dict:
    cred = session.get(Credential, credential_id)
    if cred is None:
        raise HTTPException(404, detail="credential not found")
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


__all__ = ["router"]
