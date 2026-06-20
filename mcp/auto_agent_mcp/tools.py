from __future__ import annotations

from typing import Any

from auto_agent_sdk import AutoAgent


def run_task(
    client: AutoAgent,
    *,
    prompt: str,
    url: str | None = None,
    max_steps: int = 8,
) -> dict[str, Any]:
    result = client.run_task(prompt, url=url, max_steps=max_steps)
    return result.model_dump(mode="json")


def run_workflow(
    client: AutoAgent,
    *,
    workflow_id: str,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = client.run_workflow(workflow_id, parameters=parameters)
    return result.model_dump(mode="json")


def get_run(client: AutoAgent, *, run_id: str) -> dict[str, Any]:
    result = client.get_run(run_id)
    return result.model_dump(mode="json")


def cancel_run(client: AutoAgent, *, run_id: str) -> dict[str, Any]:
    result = client.cancel_run(run_id)
    return result.model_dump(mode="json")


def list_workflows(client: AutoAgent) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in client.workflows.list()]
