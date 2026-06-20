from __future__ import annotations

import os

from app.services.credential_backends.base import (
    BackendCapabilities,
    CredentialBackend,
    CredentialNotFoundError,
    CredentialRef,
    ReadOnlyBackendError,
)

ENV_PREFIX = "AUTOAGENT_CRED_"


def _env_name_key(name: str) -> str:
    return name.upper().replace("-", "_")


def _field_prefix(name: str) -> str:
    return f"{ENV_PREFIX}{_env_name_key(name)}_"


class EnvCredentialBackend(CredentialBackend):
    """Read-only backend resolving fields from prefixed environment variables."""

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(read=True, write=False, delete=False, list=True)

    def get(self, name: str) -> dict[str, str]:
        prefix = _field_prefix(name)
        fields: dict[str, str] = {}
        for key, value in os.environ.items():
            if key.startswith(prefix):
                field = key[len(prefix) :].lower()
                fields[field] = value
        if not fields:
            raise CredentialNotFoundError(f"unknown credential {name!r}")
        return fields

    def list_refs(self) -> list[CredentialRef]:
        seen: set[str] = set()
        refs: list[CredentialRef] = []
        for key in os.environ:
            if not key.startswith(ENV_PREFIX):
                continue
            rest = key[len(ENV_PREFIX) :]
            if "_" not in rest:
                continue
            name_key = rest.rsplit("_", 1)[0]
            name = name_key.lower().replace("_", "-")
            if name not in seen:
                seen.add(name)
                refs.append(CredentialRef(name=name, mount="env"))
        return sorted(refs, key=lambda r: r.name)

    def put(self, name: str, fields: dict[str, str]) -> None:
        raise ReadOnlyBackendError("env credential backend is read-only")

    def delete(self, name: str) -> None:
        raise ReadOnlyBackendError("env credential backend is read-only")


__all__ = ["ENV_PREFIX", "EnvCredentialBackend"]
