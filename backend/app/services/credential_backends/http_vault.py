from __future__ import annotations

import json
from typing import Callable
from urllib.parse import urljoin

import httpx

from app.settings import settings
from app.services.credential_backends.base import (
    BackendCapabilities,
    CredentialBackend,
    CredentialBackendError,
    CredentialNotFoundError,
    CredentialRef,
    ReadOnlyBackendError,
)


class HttpVaultNotConfiguredError(CredentialNotFoundError):
    """Raised when the HTTP vault backend has no URL configured."""


class HttpVaultCredentialBackend(CredentialBackend):
    """Read-only adapter fetching credential fields via ``GET {url}/{name}``."""

    def __init__(
        self,
        *,
        fetch: Callable[[str], dict[str, str]] | None = None,
        url: str | None = None,
        auth_header: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._fetch = fetch
        self._url = url if url is not None else settings.http_vault_url
        self._auth_header = (
            auth_header if auth_header is not None else settings.http_vault_auth_header
        )
        self._transport = transport

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(read=True, write=False, delete=False, list=False)

    def get(self, name: str) -> dict[str, str]:
        if self._fetch is not None:
            return self._fetch(name)
        if not self._url:
            raise HttpVaultNotConfiguredError(
                "http_vault credential backend is not configured; "
                "set HTTP_VAULT_URL and HTTP_VAULT_AUTH_HEADER, "
                "or use CREDENTIAL_BACKEND=local or env"
            )
        return self._fetch_http(name)

    def _fetch_http(self, name: str) -> dict[str, str]:
        base = self._url.rstrip("/") + "/"
        target = urljoin(base, name)
        headers: dict[str, str] = {}
        if self._auth_header:
            headers["Authorization"] = self._auth_header
        try:
            with httpx.Client(transport=self._transport, timeout=15.0) as client:
                response = client.get(target, headers=headers)
        except httpx.HTTPError as exc:
            raise CredentialBackendError(
                f"http_vault request for {name!r} failed: {exc}"
            ) from exc
        if response.status_code == 404:
            raise CredentialNotFoundError(f"unknown credential {name!r}")
        if response.status_code >= 400:
            raise CredentialBackendError(
                f"http_vault request for {name!r} returned HTTP {response.status_code}"
            )
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise CredentialBackendError(
                f"http_vault response for {name!r} is not valid JSON"
            ) from exc
        if not isinstance(data, dict):
            raise CredentialBackendError(
                f"http_vault response for {name!r} is not a JSON object"
            )
        return {str(k): str(v) for k, v in data.items()}

    def put(self, name: str, fields: dict[str, str]) -> None:
        raise ReadOnlyBackendError("http_vault credential backend is read-only")

    def delete(self, name: str) -> None:
        raise ReadOnlyBackendError("http_vault credential backend is read-only")


__all__ = ["HttpVaultCredentialBackend", "HttpVaultNotConfiguredError"]
