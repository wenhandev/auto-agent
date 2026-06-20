from __future__ import annotations

from app.integrations.schema import AuthSpec, CredentialType, Field

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

_OAUTH_FIELDS = [
    Field(name="client_id", label="Client ID", kind="string", required=True),
    Field(name="client_secret", label="Client Secret", kind="secret", required=True),
]


def google_oauth_credential_type(
    *,
    type_name: str,
    label: str,
    scopes: list[str],
) -> CredentialType:
    return CredentialType(
        type=type_name,
        label=label,
        fields=list(_OAUTH_FIELDS),
        auth=AuthSpec(
            strategy="oauth2",
            authorize_url=GOOGLE_AUTHORIZE_URL,
            token_url=GOOGLE_TOKEN_URL,
            scopes=scopes,
            client_id_field="client_id",
            client_secret_field="client_secret",
            token_field="access_token",
        ),
    )


GMAIL_OAUTH2_TYPE = google_oauth_credential_type(
    type_name="gmail_oauth2",
    label="Gmail (Google OAuth2)",
    scopes=[
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.modify",
    ],
)

GOOGLE_SHEETS_OAUTH2_TYPE = google_oauth_credential_type(
    type_name="google_sheets_oauth2",
    label="Google Sheets (Google OAuth2)",
    scopes=["https://www.googleapis.com/auth/spreadsheets"],
)

__all__ = [
    "GMAIL_OAUTH2_TYPE",
    "GOOGLE_AUTHORIZE_URL",
    "GOOGLE_SHEETS_OAUTH2_TYPE",
    "GOOGLE_TOKEN_URL",
    "google_oauth_credential_type",
]
