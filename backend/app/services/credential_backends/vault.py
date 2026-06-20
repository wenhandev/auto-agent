from __future__ import annotations

from typing import Callable

from app.services.credential_backends.base import (
    BackendCapabilities,
    CredentialBackend,
    CredentialNotFoundError,
    CredentialRef,
    ReadOnlyBackendError,
)


class VaultNotImplementedError(CredentialNotFoundError):
    """Raised when the vault backend has no transport configured."""


class VaultCredentialBackend(CredentialBackend):
    """Stub for external vault integration; override ``_fetch`` in tests."""

    def __init__(
        self,
        *,
        fetch: Callable[[str], dict[str, str]] | None = None,
    ) -> None:
        self._fetch = fetch

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(read=True, write=False, delete=False, list=False)

    def get(self, name: str) -> dict[str, str]:
        if self._fetch is not None:
            return self._fetch(name)
        raise VaultNotImplementedError(
            "vault credential backend is not implemented; "
            "set CREDENTIAL_BACKEND=local or env, or configure a vault transport"
        )

    def put(self, name: str, fields: dict[str, str]) -> None:
        raise ReadOnlyBackendError("vault credential backend is read-only")

    def delete(self, name: str) -> None:
        raise ReadOnlyBackendError("vault credential backend is read-only")


__all__ = ["VaultCredentialBackend", "VaultNotImplementedError"]
