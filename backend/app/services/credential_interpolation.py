from __future__ import annotations

import json
import re
from typing import Any, Optional

from sqlmodel import Session, select

from app.db.crypto import decrypt
from app.db.models import Credential, WorkflowCredential


class CredentialResolutionError(ValueError):
    pass


TOKEN_RE = re.compile(
    r"\{\{\s*cred\.(?P<name>[A-Za-z0-9_\-]+)\.(?P<field>[A-Za-z0-9_]+)\s*\}\}"
)


def _linked_credential_ids(workflow_id: str, session: Session) -> set[str]:
    rows = session.exec(
        select(WorkflowCredential.credential_id).where(
            WorkflowCredential.workflow_id == workflow_id
        )
    ).all()
    return {r for r in rows}


def _load_fields(
    name: str,
    session: Session,
    *,
    workflow_id: Optional[str],
    allowed_ids: Optional[set[str]],
) -> dict[str, str]:
    cred = session.exec(select(Credential).where(Credential.name == name)).first()
    if cred is None:
        raise CredentialResolutionError(f"unknown credential {name!r}")
    if workflow_id is not None:
        if allowed_ids is None or cred.id not in allowed_ids:
            raise CredentialResolutionError(
                f"credential {name!r} is not linked to this workflow; "
                f"open the workflow's '凭证' panel and add it before running"
            )
    try:
        plaintext = decrypt(cred.ciphertext)
    except Exception as exc:
        raise CredentialResolutionError(
            f"credential {name!r}: decryption failed; secret key may have changed"
        ) from exc
    try:
        data = json.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise CredentialResolutionError(
            f"credential {name!r}: stored blob is not valid JSON"
        ) from exc
    if not isinstance(data, dict):
        raise CredentialResolutionError(
            f"credential {name!r}: stored blob is not an object"
        )
    return data


def _substitute_in_string(
    text: str,
    session: Session,
    cache: dict[str, dict[str, str]],
    *,
    workflow_id: Optional[str],
    allowed_ids: Optional[set[str]],
) -> str:
    def repl(match: re.Match[str]) -> str:
        name = match.group("name")
        field = match.group("field")
        if name not in cache:
            cache[name] = _load_fields(
                name,
                session,
                workflow_id=workflow_id,
                allowed_ids=allowed_ids,
            )
        fields = cache[name]
        if field not in fields:
            raise CredentialResolutionError(
                f"credential {name!r} has no field {field!r}"
            )
        return str(fields[field])

    return TOKEN_RE.sub(repl, text)


def _walk(
    value: Any,
    session: Session,
    cache: dict[str, dict[str, str]],
    *,
    workflow_id: Optional[str],
    allowed_ids: Optional[set[str]],
) -> Any:
    if isinstance(value, str):
        return _substitute_in_string(
            value,
            session,
            cache,
            workflow_id=workflow_id,
            allowed_ids=allowed_ids,
        )
    if isinstance(value, list):
        return [
            _walk(
                v,
                session,
                cache,
                workflow_id=workflow_id,
                allowed_ids=allowed_ids,
            )
            for v in value
        ]
    if isinstance(value, dict):
        return {
            k: _walk(
                v,
                session,
                cache,
                workflow_id=workflow_id,
                allowed_ids=allowed_ids,
            )
            for k, v in value.items()
        }
    return value


def resolve_params(
    params: dict[str, Any],
    session: Session,
    *,
    workflow_id: Optional[str] = None,
) -> dict[str, Any]:
    """Resolve ``{{cred.<name>.<field>}}`` tokens in a node's ``params``.

    When ``workflow_id`` is provided, only credentials linked to that
    workflow (via ``WorkflowCredential``) may be resolved. Any token
    referencing a credential that exists globally but is not linked to
    this workflow raises :class:`CredentialResolutionError`. When
    ``workflow_id`` is ``None`` the legacy behaviour applies (any
    credential by name) so ephemeral / preview runs that never persisted
    a ``Run`` row keep working.
    """
    cache: dict[str, dict[str, str]] = {}
    allowed_ids: Optional[set[str]] = None
    if workflow_id is not None:
        allowed_ids = _linked_credential_ids(workflow_id, session)
    return _walk(
        params,
        session,
        cache,
        workflow_id=workflow_id,
        allowed_ids=allowed_ids,
    )


__all__ = ["resolve_params", "CredentialResolutionError", "TOKEN_RE"]
