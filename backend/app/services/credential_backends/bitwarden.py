from __future__ import annotations

from app.services.credential_backends.base import (
    BackendCapabilities,
    CredentialBackend,
    CredentialNotFoundError,
    CredentialRef,
    ReadOnlyBackendError,
)


class BitwardenNotConfiguredError(CredentialNotFoundError):
    """Raised when the Bitwarden adapter has no CLI/session configured."""


class BitwardenCredentialBackend(CredentialBackend):
    """Stub for Bitwarden CLI/API integration."""

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(read=True, write=False, delete=False, list=True)

    def get(self, name: str) -> dict[str, str]:
        raise BitwardenNotConfiguredError(
            "bitwarden credential backend is not implemented; "
            "install the `bw` CLI, unlock a session, and configure the adapter in Settings"
        )

    def list_refs(self) -> list[CredentialRef]:
        raise BitwardenNotConfiguredError(
            "bitwarden credential backend is not implemented; "
            "install the `bw` CLI and configure the adapter in Settings"
        )

    def put(self, name: str, fields: dict[str, str]) -> None:
        raise ReadOnlyBackendError("bitwarden credential backend is read-only")

    def delete(self, name: str) -> None:
        raise ReadOnlyBackendError("bitwarden credential backend is read-only")


__all__ = ["BitwardenCredentialBackend", "BitwardenNotConfiguredError"]
