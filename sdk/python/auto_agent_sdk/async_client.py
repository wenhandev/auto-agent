from __future__ import annotations

import asyncio
import time
from typing import Any, Union

from auto_agent_sdk._http import AsyncHttpTransport
from auto_agent_sdk.models import (
    TERMINAL_RUN_STATUSES,
    RunCreate,
    RunListPage,
    RunOut,
    RunReplayResponse,
    RunTaskRequest,
    RunTaskResponse,
)
class AsyncWorkflowsClient:
    def __init__(self, http: AsyncHttpTransport) -> None:
        self._http = http

    async def list(self):
        from auto_agent_sdk.models import WorkflowListItem

        data = await self._http.request("GET", "/api/v1/workflows")
        return [WorkflowListItem.model_validate(item) for item in data]


class AsyncCredentialsClient:
    def __init__(self, http: AsyncHttpTransport) -> None:
        self._http = http

    async def list(self):
        from auto_agent_sdk.models import CredentialListItem

        data = await self._http.request("GET", "/api/v1/credentials")
        return [CredentialListItem.model_validate(item) for item in data]


class AsyncAutoAgent:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        transport: Any | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._http = AsyncHttpTransport(
            base_url=base_url,
            api_key=api_key,
            transport=transport,
            timeout=timeout,
        )
        self.workflows = AsyncWorkflowsClient(self._http)
        self.credentials = AsyncCredentialsClient(self._http)

    async def run_task(
        self,
        prompt: str,
        *,
        url: str | None = None,
        **opts: Any,
    ) -> RunTaskResponse:
        body = RunTaskRequest(prompt=prompt, url=url, **opts)
        data = await self._http.request(
            "POST",
            "/api/v1/run-task",
            json=body.model_dump(exclude_none=True),
        )
        return RunTaskResponse.model_validate(data)

    async def run_workflow(
        self,
        workflow_id: str,
        *,
        parameters: dict[str, Any] | None = None,
        browser_profile_id: str | None = None,
        totp_identifier: str | None = None,
    ) -> RunOut:
        body = RunCreate(
            parameters=parameters,
            browser_profile_id=browser_profile_id,
            totp_identifier=totp_identifier,
        )
        data = await self._http.request(
            "POST",
            f"/api/v1/workflows/{workflow_id}/run",
            json=body.model_dump(exclude_none=True),
        )
        return RunOut.model_validate(data)

    async def get_run(self, run_id: str) -> RunReplayResponse:
        data = await self._http.request("GET", f"/api/v1/runs/{run_id}")
        return RunReplayResponse.model_validate(data)

    async def list_runs(
        self,
        *,
        workflow_id: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> RunListPage:
        params: dict[str, Any] = {"limit": limit}
        if workflow_id is not None:
            params["workflow_id"] = workflow_id
        if cursor is not None:
            params["cursor"] = cursor
        data = await self._http.request("GET", "/api/v1/runs", params=params)
        return RunListPage.model_validate(data)

    async def cancel_run(self, run_id: str) -> RunOut:
        data = await self._http.request("POST", f"/api/v1/runs/{run_id}/cancel")
        return RunOut.model_validate(data)

    async def wait(
        self,
        run: Union[str, RunOut, RunTaskResponse, RunReplayResponse],
        *,
        timeout: float = 300.0,
        poll_interval: float = 1.0,
        max_interval: float = 5.0,
    ) -> RunReplayResponse:
        from auto_agent_sdk.client import _run_id

        run_id = _run_id(run)
        deadline = time.monotonic() + timeout
        interval = poll_interval
        while True:
            replay = await self.get_run(run_id)
            if replay.run.status in TERMINAL_RUN_STATUSES:
                return replay
            if time.monotonic() >= deadline:
                raise TimeoutError(f"run {run_id} did not reach terminal status within {timeout}s")
            await asyncio.sleep(interval)
            interval = min(interval * 1.5, max_interval)
