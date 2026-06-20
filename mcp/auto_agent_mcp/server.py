from __future__ import annotations

from typing import Any

from auto_agent_sdk import AutoAgent
from mcp.server.fastmcp import FastMCP

from auto_agent_mcp.config import ConfigError, McpConfig, load_config
from auto_agent_mcp import tools as tool_handlers


def create_server(config: McpConfig, *, client: AutoAgent | None = None) -> FastMCP:
    sdk = client or AutoAgent(config.base_url, config.api_key)
    mcp = FastMCP("auto-agent")

    @mcp.tool()
    def run_task(
        prompt: str,
        url: str | None = None,
        max_steps: int = 8,
    ) -> dict[str, Any]:
        """Start an ephemeral vision task via /api/v1/run-task."""
        return tool_handlers.run_task(sdk, prompt=prompt, url=url, max_steps=max_steps)

    @mcp.tool()
    def run_workflow(
        workflow_id: str,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Enqueue a workflow run via /api/v1/workflows/{id}/run."""
        return tool_handlers.run_workflow(
            sdk,
            workflow_id=workflow_id,
            parameters=parameters,
        )

    @mcp.tool()
    def get_run(run_id: str) -> dict[str, Any]:
        """Fetch run status, events, and workflow version."""
        return tool_handlers.get_run(sdk, run_id=run_id)

    @mcp.tool()
    def cancel_run(run_id: str) -> dict[str, Any]:
        """Request cancellation of a queued or running run."""
        return tool_handlers.cancel_run(sdk, run_id=run_id)

    @mcp.tool()
    def list_workflows() -> list[dict[str, Any]]:
        """List available workflows."""
        return tool_handlers.list_workflows(sdk)

    return mcp


def main() -> None:
    try:
        config = load_config()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc
    server = create_server(config)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
