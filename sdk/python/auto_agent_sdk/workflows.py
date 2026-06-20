from __future__ import annotations

from typing import Any

from auto_agent_sdk._http import HttpTransport
from auto_agent_sdk.models import WorkflowListItem


class WorkflowsClient:
    def __init__(self, http: HttpTransport) -> None:
        self._http = http

    def list(self) -> list[WorkflowListItem]:
        data = self._http.request("GET", "/api/v1/workflows")
        return [WorkflowListItem.model_validate(item) for item in data]

    def get(self, workflow_id: str) -> dict[str, Any]:
        return self._http.request("GET", f"/api/v1/workflows/{workflow_id}")
