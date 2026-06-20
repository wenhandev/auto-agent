from __future__ import annotations

from app.services.credential_backends.base import (
    BackendCapabilities,
    CredentialBackend,
    CredentialNotFoundError,
    CredentialRef,
    ReadOnlyBackendError,
)


class AzureKeyVaultNotConfiguredError(CredentialNotFoundError):
    """Raised when the Azure Key Vault adapter has no vault configured."""


class AzureKeyVaultCredentialBackend(CredentialBackend):
    """Stub for Azure Key Vault SDK integration."""

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(read=True, write=False, delete=False, list=True)

    def get(self, name: str) -> dict[str, str]:
        raise AzureKeyVaultNotConfiguredError(
            "azure_key_vault credential backend is not implemented; "
            "install azure-keyvault-secrets, configure vault access, "
            "and enable the adapter in Settings"
        )

    def list_refs(self) -> list[CredentialRef]:
        raise AzureKeyVaultNotConfiguredError(
            "azure_key_vault credential backend is not implemented; "
            "install azure-keyvault-secrets and configure the adapter in Settings"
        )

    def put(self, name: str, fields: dict[str, str]) -> None:
        raise ReadOnlyBackendError("azure_key_vault credential backend is read-only")

    def delete(self, name: str) -> None:
        raise ReadOnlyBackendError("azure_key_vault credential backend is read-only")


__all__ = ["AzureKeyVaultCredentialBackend", "AzureKeyVaultNotConfiguredError"]
