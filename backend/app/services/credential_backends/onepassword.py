from __future__ import annotations

from app.services.credential_backends.base import (
    BackendCapabilities,
    CredentialBackend,
    CredentialNotFoundError,
    CredentialRef,
    ReadOnlyBackendError,
)


class OnePasswordNotConfiguredError(CredentialNotFoundError):
    """Raised when the 1Password adapter has no CLI/Connect configured."""


class OnePasswordCredentialBackend(CredentialBackend):
    """Stub for 1Password CLI/Connect integration."""

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(read=True, write=False, delete=False, list=True)

    def get(self, name: str) -> dict[str, str]:
        raise OnePasswordNotConfiguredError(
            "onepassword credential backend is not implemented; "
            "install the `op` CLI or 1Password Connect and configure the adapter in Settings"
        )

    def list_refs(self) -> list[CredentialRef]:
        raise OnePasswordNotConfiguredError(
            "onepassword credential backend is not implemented; "
            "install the `op` CLI and configure the adapter in Settings"
        )

    def put(self, name: str, fields: dict[str, str]) -> None:
        raise ReadOnlyBackendError("onepassword credential backend is read-only")

    def delete(self, name: str) -> None:
        raise ReadOnlyBackendError("onepassword credential backend is read-only")


__all__ = ["OnePasswordCredentialBackend", "OnePasswordNotConfiguredError"]
