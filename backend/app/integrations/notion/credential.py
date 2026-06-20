from __future__ import annotations

from app.integrations.credential_types import register_credential_type
from app.integrations.schema import AuthSpec, CredentialType, Field

NOTION_VERSION = "2022-06-28"

NOTION_OAUTH2_TYPE = CredentialType(
    type="notion_oauth2",
    label="Notion (OAuth2)",
    fields=[
        Field(name="client_id", label="Client ID", kind="string", required=True),
        Field(name="client_secret", label="Client Secret", kind="secret", required=True),
    ],
    auth=AuthSpec(
        strategy="oauth2",
        authorize_url="https://api.notion.com/v1/oauth/authorize",
        token_url="https://api.notion.com/v1/oauth/token",
        scopes=[],
        client_id_field="client_id",
        client_secret_field="client_secret",
        token_field="access_token",
    ),
)

NOTION_INTERNAL_TOKEN_TYPE = CredentialType(
    type="notion_internal_token",
    label="Notion Internal Integration Token",
    fields=[
        Field(name="token", label="Integration Token", kind="secret", required=True),
    ],
    auth=AuthSpec(strategy="bearer", token_field="token"),
)


def register() -> None:
    register_credential_type(NOTION_OAUTH2_TYPE)
    register_credential_type(NOTION_INTERNAL_TOKEN_TYPE)


__all__ = [
    "NOTION_INTERNAL_TOKEN_TYPE",
    "NOTION_OAUTH2_TYPE",
    "NOTION_VERSION",
    "register",
]
