from __future__ import annotations

import json

from sqlmodel import Session, select

from app.db.crypto import decrypt, encrypt
from app.db.models import Credential
from app.services.credential_backends.base import (
    BackendCapabilities,
    CredentialBackend,
    CredentialNotFoundError,
    CredentialRef,
)


class LocalCredentialBackend(CredentialBackend):
    """Fernet-backed vault — the default, behaviour-preserving backend."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(read=True, write=True, delete=True, list=True)

    def get(self, name: str) -> dict[str, str]:
        cred = self._session.exec(
            select(Credential).where(Credential.name == name)
        ).first()
        if cred is None:
            raise CredentialNotFoundError(f"unknown credential {name!r}")
        try:
            plaintext = decrypt(cred.ciphertext)
        except Exception as exc:
            raise CredentialNotFoundError(
                f"credential {name!r}: decryption failed; secret key may have changed"
            ) from exc
        try:
            data = json.loads(plaintext.decode("utf-8"))
        except Exception as exc:
            raise CredentialNotFoundError(
                f"credential {name!r}: stored blob is not valid JSON"
            ) from exc
        if not isinstance(data, dict):
            raise CredentialNotFoundError(
                f"credential {name!r}: stored blob is not an object"
            )
        return {str(k): str(v) for k, v in data.items()}

    def list_refs(self) -> list[CredentialRef]:
        rows = self._session.exec(
            select(Credential).order_by(Credential.name)  # type: ignore[attr-defined]
        ).all()
        return [CredentialRef(name=r.name, mount="local") for r in rows]

    def put(self, name: str, fields: dict[str, str]) -> None:
        cred = self._session.exec(
            select(Credential).where(Credential.name == name)
        ).first()
        blob = encrypt(json.dumps(fields, ensure_ascii=False).encode("utf-8"))
        if cred is None:
            cred = Credential(name=name, ciphertext=blob)
            self._session.add(cred)
        else:
            cred.ciphertext = blob
            self._session.add(cred)
        self._session.commit()

    def delete(self, name: str) -> None:
        cred = self._session.exec(
            select(Credential).where(Credential.name == name)
        ).first()
        if cred is None:
            raise CredentialNotFoundError(f"unknown credential {name!r}")
        self._session.delete(cred)
        self._session.commit()


__all__ = ["LocalCredentialBackend"]
