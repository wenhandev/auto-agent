from app.services.credential_backends.base import (
    BackendCapabilities,
    CredentialBackend,
    CredentialBackendError,
    CredentialNotFoundError,
    CredentialRef,
    ReadOnlyBackendError,
)
from app.services.credential_backends.azure_key_vault import (
    AzureKeyVaultCredentialBackend,
    AzureKeyVaultNotConfiguredError,
)
from app.services.credential_backends.bitwarden import (
    BitwardenCredentialBackend,
    BitwardenNotConfiguredError,
)
from app.services.credential_backends.env import ENV_PREFIX, EnvCredentialBackend
from app.services.credential_backends.http_vault import (
    HttpVaultCredentialBackend,
    HttpVaultNotConfiguredError,
)
from app.services.credential_backends.local import LocalCredentialBackend
from app.services.credential_backends.onepassword import (
    OnePasswordCredentialBackend,
    OnePasswordNotConfiguredError,
)
from app.services.credential_backends.registry import (
    VALID_BACKENDS,
    CredentialBackendRegistry,
    create_registry,
)
from app.services.credential_backends.vault import (
    VaultCredentialBackend,
    VaultNotImplementedError,
)

__all__ = [
    "ENV_PREFIX",
    "VALID_BACKENDS",
    "AzureKeyVaultCredentialBackend",
    "AzureKeyVaultNotConfiguredError",
    "BackendCapabilities",
    "BitwardenCredentialBackend",
    "BitwardenNotConfiguredError",
    "CredentialBackend",
    "CredentialBackendError",
    "CredentialBackendRegistry",
    "CredentialNotFoundError",
    "CredentialRef",
    "EnvCredentialBackend",
    "HttpVaultCredentialBackend",
    "HttpVaultNotConfiguredError",
    "LocalCredentialBackend",
    "OnePasswordCredentialBackend",
    "OnePasswordNotConfiguredError",
    "ReadOnlyBackendError",
    "VaultCredentialBackend",
    "VaultNotImplementedError",
    "create_registry",
]
