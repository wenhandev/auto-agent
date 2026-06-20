from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

from app.integrations.credential_types import get_credential_type
from app.integrations.schema import AuthSpec, CredentialType


@dataclass
class RenderedRequest:
    method: str
    url: str
    query: dict[str, str]
    headers: dict[str, str]
    body: Any
    body_kind: str
    secret_keys: set[str] = field(default_factory=set)


def _mark_secret(keys: set[str], key: str) -> None:
    keys.add(key)


async def inject_auth(
    req: RenderedRequest,
    *,
    cred_type: CredentialType,
    cred_fields: dict[str, str],
    oauth_token: str | None = None,
) -> None:
    """Mutate *req* in place, tagging injected values in *secret_keys*."""
    auth = cred_type.auth
    keys = req.secret_keys

    if auth.strategy == "none":
        return

    if auth.strategy == "api_key_header":
        if not auth.header_name or not auth.key_field:
            raise ValueError("api_key_header requires header_name and key_field")
        val = cred_fields.get(auth.key_field, "")
        req.headers[auth.header_name] = val
        _mark_secret(keys, f"header.{auth.header_name}")
        return

    if auth.strategy == "api_key_query":
        if not auth.query_name or not auth.key_field:
            raise ValueError("api_key_query requires query_name and key_field")
        val = cred_fields.get(auth.key_field, "")
        req.query[auth.query_name] = val
        _mark_secret(keys, f"query.{auth.query_name}")
        return

    if auth.strategy == "bearer":
        token_field = auth.token_field or "access_token"
        token = oauth_token or cred_fields.get(token_field, "")
        if not token:
            raise ValueError(f"bearer auth missing token field {token_field!r}")
        req.headers["Authorization"] = f"Bearer {token}"
        _mark_secret(keys, "header.Authorization")
        return

    if auth.strategy == "basic":
        if not auth.username_field or not auth.password_field:
            raise ValueError("basic auth requires username_field and password_field")
        user = cred_fields.get(auth.username_field, "")
        password = cred_fields.get(auth.password_field, "")
        encoded = base64.b64encode(f"{user}:{password}".encode()).decode()
        req.headers["Authorization"] = f"Basic {encoded}"
        _mark_secret(keys, "header.Authorization")
        return

    if auth.strategy == "oauth2":
        token_field = auth.token_field or "access_token"
        token = oauth_token or cred_fields.get(token_field, "")
        if not token:
            raise ValueError("oauth2 credential is not connected; complete OAuth connect first")
        req.headers["Authorization"] = f"Bearer {token}"
        _mark_secret(keys, "header.Authorization")
        return

    raise ValueError(f"unsupported auth strategy {auth.strategy!r}")


def resolve_cred_type(type_name: str) -> CredentialType:
    ct = get_credential_type(type_name)
    if ct is None:
        raise ValueError(f"unknown credential type {type_name!r}")
    return ct


__all__ = ["RenderedRequest", "inject_auth", "resolve_cred_type"]
