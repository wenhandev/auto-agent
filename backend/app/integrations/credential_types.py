from __future__ import annotations

from app.integrations.schema import AuthSpec, CredentialType, Field

GENERIC_CREDENTIAL_TYPE = CredentialType(
    type="generic",
    label="Generic key-value",
    fields=[],
    auth=AuthSpec(strategy="none"),
)

FIXTURE_API_KEY_TYPE = CredentialType(
    type="fixture_api_key",
    label="Fixture API Key",
    fields=[
        Field(name="api_key", label="API Key", kind="secret", required=True),
    ],
    auth=AuthSpec(
        strategy="api_key_header",
        header_name="X-Api-Key",
        key_field="api_key",
    ),
)

FIXTURE_BEARER_TYPE = CredentialType(
    type="fixture_bearer",
    label="Fixture Bearer Token",
    fields=[
        Field(name="token", label="Token", kind="secret", required=True),
    ],
    auth=AuthSpec(strategy="bearer", token_field="token"),
)

FIXTURE_BASIC_TYPE = CredentialType(
    type="fixture_basic",
    label="Fixture Basic Auth",
    fields=[
        Field(name="username", label="Username", kind="string", required=True),
        Field(name="password", label="Password", kind="secret", required=True),
    ],
    auth=AuthSpec(
        strategy="basic",
        username_field="username",
        password_field="password",
    ),
)

TOTP_CREDENTIAL_TYPE = CredentialType(
    type="totp",
    label="TOTP (2FA)",
    fields=[
        Field(name="totp_secret", label="Secret (base32)", kind="secret", required=True),
        Field(name="digits", label="Digits", kind="number", required=False, default=6),
        Field(name="period", label="Period (seconds)", kind="number", required=False, default=30),
        Field(
            name="algorithm",
            label="Algorithm",
            kind="string",
            required=False,
            default="sha1",
        ),
    ],
    auth=AuthSpec(strategy="none"),
)

CREDIT_CARD_CREDENTIAL_TYPE = CredentialType(
    type="credit_card",
    label="Credit card",
    fields=[
        Field(name="number", label="Card number", kind="secret", required=True),
        Field(name="exp_month", label="Expiry month", kind="string", required=True),
        Field(name="exp_year", label="Expiry year", kind="string", required=True),
        Field(name="cvc", label="CVC", kind="secret", required=True),
        Field(name="holder_name", label="Cardholder name", kind="string", required=False),
        Field(name="zip", label="Billing ZIP", kind="string", required=False),
    ],
    auth=AuthSpec(strategy="none"),
)

FIXTURE_OAUTH2_TYPE = CredentialType(
    type="fixture_oauth2",
    label="Fixture OAuth2",
    fields=[
        Field(name="client_id", label="Client ID", kind="string", required=True),
        Field(name="client_secret", label="Client Secret", kind="secret", required=True),
    ],
    auth=AuthSpec(
        strategy="oauth2",
        authorize_url="https://oauth.fixture.example.com/authorize",
        token_url="https://oauth.fixture.example.com/token",
        scopes=["read"],
        client_id_field="client_id",
        client_secret_field="client_secret",
        token_field="access_token",
    ),
)

_BUILTIN_TYPES: dict[str, CredentialType] = {
    GENERIC_CREDENTIAL_TYPE.type: GENERIC_CREDENTIAL_TYPE,
    TOTP_CREDENTIAL_TYPE.type: TOTP_CREDENTIAL_TYPE,
    CREDIT_CARD_CREDENTIAL_TYPE.type: CREDIT_CARD_CREDENTIAL_TYPE,
    FIXTURE_API_KEY_TYPE.type: FIXTURE_API_KEY_TYPE,
    FIXTURE_BEARER_TYPE.type: FIXTURE_BEARER_TYPE,
    FIXTURE_BASIC_TYPE.type: FIXTURE_BASIC_TYPE,
    FIXTURE_OAUTH2_TYPE.type: FIXTURE_OAUTH2_TYPE,
}


def get_credential_type(type_name: str) -> CredentialType | None:
    return _BUILTIN_TYPES.get(type_name)


def list_credential_types() -> list[CredentialType]:
    return list(_BUILTIN_TYPES.values())


def register_credential_type(ct: CredentialType) -> None:
    _BUILTIN_TYPES[ct.type] = ct


__all__ = [
    "CREDIT_CARD_CREDENTIAL_TYPE",
    "TOTP_CREDENTIAL_TYPE",
    "FIXTURE_API_KEY_TYPE",
    "FIXTURE_BASIC_TYPE",
    "FIXTURE_BEARER_TYPE",
    "FIXTURE_OAUTH2_TYPE",
    "GENERIC_CREDENTIAL_TYPE",
    "get_credential_type",
    "list_credential_types",
    "register_credential_type",
]
