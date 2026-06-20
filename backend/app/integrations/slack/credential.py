from __future__ import annotations

from app.integrations.credential_types import register_credential_type
from app.integrations.schema import AuthSpec, CredentialType, Field

SLACK_OAUTH2_TYPE = CredentialType(
    type="slack_oauth2",
    label="Slack Bot (OAuth2)",
    fields=[
        Field(name="client_id", label="Client ID", kind="string", required=True),
        Field(name="client_secret", label="Client Secret", kind="secret", required=True),
    ],
    auth=AuthSpec(
        strategy="oauth2",
        authorize_url="https://slack.com/oauth/v2/authorize",
        token_url="https://slack.com/api/oauth.v2.access",
        scopes=[
            "chat:write",
            "channels:read",
            "channels:history",
            "users:read",
            "files:write",
        ],
        client_id_field="client_id",
        client_secret_field="client_secret",
        token_field="access_token",
    ),
)


def register() -> None:
    register_credential_type(SLACK_OAUTH2_TYPE)


__all__ = ["SLACK_OAUTH2_TYPE", "register"]
