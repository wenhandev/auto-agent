"""Tests for MCP tool handlers and configuration."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SDK_ROOT = _REPO_ROOT / "sdk" / "python"
_MCP_ROOT = _REPO_ROOT / "mcp"
for path in (_SDK_ROOT, _MCP_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from auto_agent_mcp.config import ConfigError, load_config
from auto_agent_mcp import tools as mcp_tools
from auto_agent_mcp.server import create_server
from auto_agent_sdk.models import RunOut, RunReplayResponse, RunTaskResponse, WorkflowListItem


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def test_load_config_requires_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTO_AGENT_BASE_URL", raising=False)
    monkeypatch.delenv("AUTO_AGENT_API_KEY", raising=False)
    with pytest.raises(ConfigError) as exc:
        load_config()
    msg = str(exc.value)
    assert "AUTO_AGENT_BASE_URL" in msg
    assert "AUTO_AGENT_API_KEY" in msg


def test_load_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_AGENT_BASE_URL", "http://localhost:8000/")
    monkeypatch.setenv("AUTO_AGENT_API_KEY", "sk_test")
    cfg = load_config()
    assert cfg.base_url == "http://localhost:8000/"
    assert cfg.api_key == "sk_test"


def _mock_client() -> MagicMock:
    client = MagicMock()
    client.run_task.return_value = RunTaskResponse(run_id="run-1", status="queued")
    client.run_workflow.return_value = RunOut(
        id="run-2",
        workflow_id="wf-1",
        workflow_version_id="wv-1",
        status="queued",
        queued_at=_utcnow(),
    )
    client.get_run.return_value = RunReplayResponse(
        run=client.run_workflow.return_value,
        workflow_version={
            "id": "wv-1",
            "workflow_id": "wf-1",
            "version_index": 1,
            "authored_by": "manual",
            "workflow": {"nodes": [], "edges": [], "start_id": "start", "parameters": []},
            "created_at": _utcnow(),
        },
        events=[],
    )
    client.cancel_run.return_value = RunOut(
        id="run-1",
        workflow_id="wf-1",
        workflow_version_id="wv-1",
        status="aborted",
        queued_at=_utcnow(),
    )
    client.workflows.list.return_value = [
        WorkflowListItem(
            id="wf-1",
            name="demo",
            description=None,
            current_version_index=1,
            last_run_status="completed",
            updated_at=_utcnow(),
        )
    ]
    return client


def test_mcp_run_task_handler() -> None:
    client = _mock_client()
    result = mcp_tools.run_task(client, prompt="find title", url="https://example.com")
    client.run_task.assert_called_once_with("find title", url="https://example.com", max_steps=8)
    assert result["run_id"] == "run-1"


def test_mcp_run_workflow_handler() -> None:
    client = _mock_client()
    result = mcp_tools.run_workflow(client, workflow_id="wf-1", parameters={"a": 1})
    client.run_workflow.assert_called_once_with("wf-1", parameters={"a": 1})
    assert result["id"] == "run-2"


def test_mcp_get_run_handler() -> None:
    client = _mock_client()
    result = mcp_tools.get_run(client, run_id="run-1")
    client.get_run.assert_called_once_with("run-1")
    assert result["run"]["status"] == "queued"


def test_mcp_cancel_run_handler() -> None:
    client = _mock_client()
    result = mcp_tools.cancel_run(client, run_id="run-1")
    client.cancel_run.assert_called_once_with("run-1")
    assert result["status"] == "aborted"


def test_mcp_list_workflows_handler() -> None:
    client = _mock_client()
    result = mcp_tools.list_workflows(client)
    client.workflows.list.assert_called_once_with()
    assert result[0]["name"] == "demo"


def test_create_server_exposes_five_tools() -> None:
    from auto_agent_mcp.config import McpConfig

    server = create_server(McpConfig(base_url="http://localhost:8000", api_key="sk_test"), client=_mock_client())
    tool_names = {tool.name for tool in server._tool_manager.list_tools()}  # type: ignore[attr-defined]
    assert tool_names == {
        "run_task",
        "run_workflow",
        "get_run",
        "cancel_run",
        "list_workflows",
    }
