from __future__ import annotations

from typing import Optional

from sqlmodel import Session, select

from app.db.models import Credential
from app.settings import settings
from app.services.credential_backends.base import (
    CredentialBackend,
    CredentialBackendError,
    CredentialNotFoundError,
)
from app.services.credential_backends.azure_key_vault import AzureKeyVaultCredentialBackend
from app.services.credential_backends.bitwarden import BitwardenCredentialBackend
from app.services.credential_backends.env import EnvCredentialBackend
from app.services.credential_backends.http_vault import HttpVaultCredentialBackend
from app.services.credential_backends.local import LocalCredentialBackend
from app.services.credential_backends.onepassword import OnePasswordCredentialBackend
from app.services.credential_backends.vault import VaultCredentialBackend

VALID_BACKENDS = frozenset({"local", "env", "vault"})

_DEFAULT_BACKENDS: dict[str, type[CredentialBackend]] = {
    "local": LocalCredentialBackend,
    "env": EnvCredentialBackend,
    "vault": VaultCredentialBackend,
    "bitwarden": BitwardenCredentialBackend,
    "onepassword": OnePasswordCredentialBackend,
    "azure_key_vault": AzureKeyVaultCredentialBackend,
    "http_vault": HttpVaultCredentialBackend,
}


def _build_default_backends(session: Session) -> dict[str, CredentialBackend]:
    backends: dict[str, CredentialBackend] = {}
    for mount, cls in _DEFAULT_BACKENDS.items():
        if cls is LocalCredentialBackend:
            backends[mount] = LocalCredentialBackend(session)
        else:
            backends[mount] = cls()
    return backends


class CredentialBackendRegistry:
    """Named mounts with a default; routes resolution to the active backend."""

    def __init__(
        self,
        session: Session,
        *,
        default_mount: str | None = None,
        backends: dict[str, CredentialBackend] | None = None,
    ) -> None:
        self._session = session
        mount = (default_mount or settings.credential_backend or "local").lower()
        if mount not in VALID_BACKENDS:
            mount = "local"
        self._default_mount = mount
        self._backends: dict[str, CredentialBackend] = (
            backends or _build_default_backends(session)
        )
        self._cache: dict[str, dict[str, str]] = {}

    @property
    def default_mount(self) -> str:
        return self._default_mount

    def get_backend(self, mount: str | None = None) -> CredentialBackend:
        key = (mount or self._default_mount).lower()
        backend = self._backends.get(key)
        if backend is None:
            raise CredentialBackendError(f"unknown credential backend mount {key!r}")
        return backend

    def clear_cache(self) -> None:
        self._cache.clear()

    def resolve_fields(
        self,
        name: str,
        *,
        mount: str | None = None,
        workflow_id: str | None = None,
        allowed_ids: set[str] | None = None,
    ) -> dict[str, str]:
        """Load all fields for a credential, with per-run caching."""
        resolved_mount = (mount or self._default_mount).lower()
        cache_key = f"{resolved_mount}:{name}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if resolved_mount == "local" and workflow_id is not None:
            self._enforce_local_link(name, allowed_ids)

        backend = self.get_backend(resolved_mount)
        try:
            fields = backend.get(name)
        except CredentialNotFoundError:
            raise
        except Exception as exc:
            raise CredentialBackendError(
                f"credential {name!r} on mount {resolved_mount!r}: {exc}"
            ) from exc

        self._cache[cache_key] = fields
        return fields

    def resolve_field(
        self,
        name: str,
        field: str,
        *,
        mount: str | None = None,
        workflow_id: str | None = None,
        allowed_ids: set[str] | None = None,
    ) -> str:
        fields = self.resolve_fields(
            name,
            mount=mount,
            workflow_id=workflow_id,
            allowed_ids=allowed_ids,
        )
        if field not in fields:
            raise CredentialBackendError(
                f"credential {name!r} has no field {field!r}"
            )
        return str(fields[field])

    def _enforce_local_link(
        self,
        name: str,
        allowed_ids: set[str] | None,
    ) -> None:
        cred = self._session.exec(
            select(Credential).where(Credential.name == name)
        ).first()
        if cred is None:
            raise CredentialNotFoundError(f"unknown credential {name!r}")
        if allowed_ids is None or cred.id not in allowed_ids:
            raise CredentialBackendError(
                f"credential {name!r} is not linked to this workflow; "
                f"open the workflow's '凭证' panel and add it before running"
            )


def create_registry(
    session: Session,
    *,
    default_mount: str | None = None,
    backends: dict[str, CredentialBackend] | None = None,
) -> CredentialBackendRegistry:
    return CredentialBackendRegistry(
        session,
        default_mount=default_mount,
        backends=backends,
    )


__all__ = [
    "VALID_BACKENDS",
    "CredentialBackendRegistry",
    "create_registry",
]
