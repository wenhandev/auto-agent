from __future__ import annotations

from typing import Any, Optional

from sqlmodel import Session

from app.services.credential_service import (
    TOKEN_RE,
    CredentialResolutionError,
    make_resolver,
    walk_and_substitute,
)


def make_token_resolver(
    session: Session,
    *,
    workflow_id: Optional[str] = None,
):
    """Return a ``resolve(name, field) -> str`` or ``resolve(mount, name, field)`` callable.

    Shares one decrypt cache and one linked-id check across all tokens in a
    node's params. Used by the chained ``variable_interpolation`` pass so
    credential and node-output tokens resolve in a single tree walk.
    """
    resolver = make_resolver(session, workflow_id=workflow_id)

    def resolve(name_or_mount: str, field_or_name: str, field: str | None = None) -> str:
        if field is None:
            return resolver.resolve(name_or_mount, field_or_name)
        return resolver.resolve(field_or_name, field, mount=name_or_mount)

    def resolve_token_middle(name_part: str, fld: str) -> str:
        return resolver.resolve_token_middle(name_part, fld)

    resolve.resolve_token_middle = resolve_token_middle  # type: ignore[attr-defined]
    return resolve


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
    resolver = make_resolver(session, workflow_id=workflow_id)
    return walk_and_substitute(params, resolver)


__all__ = [
    "resolve_params",
    "make_token_resolver",
    "CredentialResolutionError",
    "TOKEN_RE",
]
