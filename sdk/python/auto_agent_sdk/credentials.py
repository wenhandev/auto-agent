from __future__ import annotations

from auto_agent_sdk._http import HttpTransport
from auto_agent_sdk.models import CredentialListItem


class CredentialsClient:
    def __init__(self, http: HttpTransport) -> None:
        self._http = http

    def list(self) -> list[CredentialListItem]:
        data = self._http.request("GET", "/api/v1/credentials")
        return [CredentialListItem.model_validate(item) for item in data]
