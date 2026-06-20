from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field as PydanticField


class Opt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    label: str
    value: Any


FieldKind = Literal[
    "string",
    "number",
    "boolean",
    "options",
    "collection",
    "json",
    "secret",
    "oauth2",
]


class Field(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    label: str
    kind: FieldKind
    required: bool = False
    options: list[Opt] | None = None
    default: Any = None


class RequestTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    url: str
    query: dict[str, str] = PydanticField(default_factory=dict)
    headers: dict[str, str] = PydanticField(default_factory=dict)
    body: dict[str, Any] | str | None = None
    body_type: Literal["json", "form", "raw"] = "json"


class Pagination(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["cursor", "offset", "link_header"]
    cursor_path: str | None = None
    cursor_param: str | None = None
    cursor_location: Literal["query", "body"] = "query"
    offset_param: str | None = None
    limit_param: str | None = None
    page_size: int = PydanticField(default=100, ge=1, le=1000)
    max_pages: int = PydanticField(default=10, ge=1, le=100)
    link_header_rel: str = "next"


class ResponseMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_path: str | None = None
    root_path: str | None = None
    pagination: Pagination | None = None


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    label: str
    fields: list[Field] = PydanticField(default_factory=list)
    request: RequestTemplate
    response: ResponseMap


class Resource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    label: str
    operations: list[Operation]


VerificationType = Literal["hmac", "shared_secret", "challenge"]


class VerificationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: VerificationType
    header: str | None = None
    algorithm: str = "sha256"
    challenge_field: str | None = None
    challenge_response_field: str | None = None
    secret_header: str | None = None
    event_id_path: str | None = None


TriggerKind = Literal["poll", "webhook"]


class TriggerDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    label: str
    kind: TriggerKind
    resource: str | None = None
    list_operation: str | None = None
    dedup_path: str | None = None
    item_path: str | None = None
    cursor_param: str | None = None
    subscribe_operation: str | None = None
    unsubscribe_operation: str | None = None
    event_item_path: str | None = None
    verification: VerificationSpec | None = None


class IntegrationDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app: str
    version: str
    credentials: list[str] = PydanticField(default_factory=list)
    resources: list[Resource]
    triggers: list[TriggerDescriptor] = PydanticField(default_factory=list)


AuthStrategy = Literal[
    "api_key_header",
    "api_key_query",
    "bearer",
    "basic",
    "oauth2",
    "none",
]


class AuthSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: AuthStrategy = "none"
    header_name: str | None = None
    query_name: str | None = None
    key_field: str | None = None
    token_field: str | None = None
    username_field: str | None = None
    password_field: str | None = None
    authorize_url: str | None = None
    token_url: str | None = None
    scopes: list[str] = PydanticField(default_factory=list)
    client_id_field: str | None = None
    client_secret_field: str | None = None


class CredentialType(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    label: str = ""
    fields: list[Field] = PydanticField(default_factory=list)
    auth: AuthSpec = PydanticField(default_factory=lambda: AuthSpec(strategy="none"))


class IntegrationCatalogueEntry(BaseModel):
    app: str
    version: str
    credentials: list[str] = PydanticField(default_factory=list)
    resources: list[dict[str, Any]]
    triggers: list[dict[str, Any]] = PydanticField(default_factory=list)


__all__ = [
    "AuthSpec",
    "AuthStrategy",
    "CredentialType",
    "Field",
    "FieldKind",
    "IntegrationCatalogueEntry",
    "IntegrationDescriptor",
    "Operation",
    "Opt",
    "Pagination",
    "RequestTemplate",
    "Resource",
    "ResponseMap",
    "TriggerDescriptor",
    "TriggerKind",
    "VerificationSpec",
    "VerificationType",
]
