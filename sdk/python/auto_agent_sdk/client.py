from __future__ import annotations

import time
from typing import Any, Optional, Union

from auto_agent_sdk._http import HttpTransport
from auto_agent_sdk.credentials import CredentialsClient
from auto_agent_sdk.models import (
    TERMINAL_RUN_STATUSES,
    RunCreate,
    RunListPage,
    RunOut,
    RunReplayResponse,
    RunTaskRequest,
    RunTaskResponse,
)
from auto_agent_sdk.workflows import WorkflowsClient


class AutoAgent:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        transport: Any | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._http = HttpTransport(
            base_url=base_url,
            api_key=api_key,
            transport=transport,
            timeout=timeout,
        )
        self.workflows = WorkflowsClient(self._http)
        self.credentials = CredentialsClient(self._http)

    def run_task(
        self,
        prompt: str,
        *,
        url: str | None = None,
        **opts: Any,
    ) -> RunTaskResponse:
        body = RunTaskRequest(prompt=prompt, url=url, **opts)
        data = self._http.request(
            "POST",
            "/api/v1/run-task",
            json=body.model_dump(exclude_none=True),
        )
        return RunTaskResponse.model_validate(data)

    def run_workflow(
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
        data = self._http.request(
            "POST",
            f"/api/v1/workflows/{workflow_id}/run",
            json=body.model_dump(exclude_none=True),
        )
        return RunOut.model_validate(data)

    def get_run(self, run_id: str) -> RunReplayResponse:
        data = self._http.request("GET", f"/api/v1/runs/{run_id}")
        return RunReplayResponse.model_validate(data)

    def list_runs(
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
        data = self._http.request("GET", "/api/v1/runs", params=params)
        return RunListPage.model_validate(data)

    def cancel_run(self, run_id: str) -> RunOut:
        data = self._http.request("POST", f"/api/v1/runs/{run_id}/cancel")
        return RunOut.model_validate(data)

    def wait(
        self,
        run: Union[str, RunOut, RunTaskResponse, RunReplayResponse],
        *,
        timeout: float = 300.0,
        poll_interval: float = 1.0,
        max_interval: float = 5.0,
    ) -> RunReplayResponse:
        run_id = _run_id(run)
        deadline = time.monotonic() + timeout
        interval = poll_interval
        while True:
            replay = self.get_run(run_id)
            if replay.run.status in TERMINAL_RUN_STATUSES:
                return replay
            if time.monotonic() >= deadline:
                raise TimeoutError(f"run {run_id} did not reach terminal status within {timeout}s")
            time.sleep(interval)
            interval = min(interval * 1.5, max_interval)


def _run_id(run: Union[str, RunOut, RunTaskResponse, RunReplayResponse]) -> str:
    if isinstance(run, str):
        return run
    if isinstance(run, RunTaskResponse):
        return run.run_id
    if isinstance(run, RunReplayResponse):
        return run.run.id
    return run.id
