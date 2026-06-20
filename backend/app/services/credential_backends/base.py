from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import NamedTuple


class CredentialBackendError(Exception):
    """Base error for credential backend operations."""


class CredentialNotFoundError(CredentialBackendError):
    """Raised when a credential name is unknown to the backend."""


class ReadOnlyBackendError(CredentialBackendError):
    """Raised when a write is attempted against a read-only backend."""


class CredentialRef(NamedTuple):
    name: str
    mount: str | None = None


@dataclass(frozen=True)
class BackendCapabilities:
    read: bool = True
    write: bool = False
    delete: bool = False
    list: bool = True


class CredentialBackend(ABC):
    @property
    @abstractmethod
    def capabilities(self) -> BackendCapabilities:
        raise NotImplementedError

    @abstractmethod
    def get(self, name: str) -> dict[str, str]:
        raise NotImplementedError

    def list_refs(self) -> list[CredentialRef]:
        if not self.capabilities.list:
            return []
        raise NotImplementedError

    def put(self, name: str, fields: dict[str, str]) -> None:
        if not self.capabilities.write:
            raise ReadOnlyBackendError(
                f"backend {self.__class__.__name__!r} is read-only"
            )
        raise NotImplementedError

    def delete(self, name: str) -> None:
        if not self.capabilities.delete:
            raise ReadOnlyBackendError(
                f"backend {self.__class__.__name__!r} is read-only"
            )
        raise NotImplementedError


__all__ = [
    "BackendCapabilities",
    "CredentialBackend",
    "CredentialBackendError",
    "CredentialNotFoundError",
    "CredentialRef",
    "ReadOnlyBackendError",
]
