from __future__ import annotations

import re
from typing import Any, Optional

from sqlmodel import Session, select

from app.db.models import WorkflowCredential
from app.services.credential_backends.base import (
    CredentialBackendError,
    CredentialNotFoundError,
)
from app.services.credential_backends.registry import create_registry


class CredentialResolutionError(ValueError):
    pass

# {{cred.<name>.<field>}} or {{cred.<mount>:<name>.<field>}}
TOKEN_RE = re.compile(
    r"\{\{\s*cred\.(?:(?P<mount>[A-Za-z0-9_\-]+):)?"
    r"(?P<name>[A-Za-z0-9_\-]+)\.(?P<field>[A-Za-z0-9_]+)\s*\}\}"
)


def parse_cred_token(name_part: str) -> tuple[str | None, str]:
    """Split ``mount:name`` or plain ``name`` from a cred token middle segment."""
    if ":" in name_part:
        mount, name = name_part.split(":", 1)
        return mount, name
    return None, name_part


def _linked_credential_ids(workflow_id: str, session: Session) -> set[str]:
    try:
        rows = session.exec(
            select(WorkflowCredential.credential_id).where(
                WorkflowCredential.workflow_id == workflow_id
            )
        ).all()
        return {r for r in rows}
    except Exception:
        # Desktop worker bundles may not ship cloud SQLite tables.
        return set()


class CredentialResolver:
    """Unified credential resolution path for interpolation and nodes."""

    def __init__(
        self,
        session: Session,
        *,
        workflow_id: Optional[str] = None,
        default_mount: str | None = None,
    ) -> None:
        self._session = session
        self._workflow_id = workflow_id
        self._registry = create_registry(session, default_mount=default_mount)
        self._allowed_ids: set[str] | None = None
        if workflow_id is not None:
            self._allowed_ids = _linked_credential_ids(workflow_id, session)

    @property
    def default_mount(self) -> str:
        return self._registry.default_mount

    def resolve(
        self,
        name: str,
        field: str,
        *,
        mount: str | None = None,
    ) -> str:
        try:
            return self._registry.resolve_field(
                name,
                field,
                mount=mount,
                workflow_id=self._workflow_id,
                allowed_ids=self._allowed_ids,
            )
        except CredentialNotFoundError as exc:
            raise CredentialResolutionError(str(exc)) from exc
        except CredentialBackendError as exc:
            raise CredentialResolutionError(str(exc)) from exc

    def resolve_token_middle(self, name_part: str, field: str) -> str:
        mount, name = parse_cred_token(name_part)
        return self.resolve(name, field, mount=mount)


def make_resolver(
    session: Session,
    *,
    workflow_id: Optional[str] = None,
    default_mount: str | None = None,
) -> CredentialResolver:
    return CredentialResolver(
        session,
        workflow_id=workflow_id,
        default_mount=default_mount,
    )


def substitute_cred_tokens_in_string(
    text: str,
    resolver: CredentialResolver,
) -> str:
    def repl(match: re.Match[str]) -> str:
        mount = match.group("mount")
        name = match.group("name")
        field = match.group("field")
        return resolver.resolve(name, field, mount=mount)

    return TOKEN_RE.sub(repl, text)


def walk_and_substitute(
    value: Any,
    resolver: CredentialResolver,
) -> Any:
    if isinstance(value, str):
        return substitute_cred_tokens_in_string(value, resolver)
    if isinstance(value, list):
        return [walk_and_substitute(v, resolver) for v in value]
    if isinstance(value, dict):
        return {k: walk_and_substitute(v, resolver) for k, v in value.items()}
    return value


__all__ = [
    "CredentialResolver",
    "TOKEN_RE",
    "make_resolver",
    "parse_cred_token",
    "substitute_cred_tokens_in_string",
    "walk_and_substitute",
]
