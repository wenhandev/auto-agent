"""Tests for the auto-agent CLI."""

from __future__ import annotations

import json
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SDK_ROOT = _REPO_ROOT / "sdk" / "python"
if str(_SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(_SDK_ROOT))

from auto_agent_sdk.cli import build_parser, main, run_command
from auto_agent_sdk.config import ConfigError, load_config
from auto_agent_sdk.models import RunListPage, RunOut, RunReplayResponse, RunTaskResponse


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _run_out(run_id: str = "run-1", status: str = "queued") -> RunOut:
    return RunOut(
        id=run_id,
        workflow_id="wf-1",
        workflow_version_id="wv-1",
        status=status,  # type: ignore[arg-type]
        queued_at=_utcnow(),
    )


def _replay(run_id: str = "run-1", status: str = "completed") -> RunReplayResponse:
    return RunReplayResponse(
        run=_run_out(run_id, status),
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


def _mock_client() -> MagicMock:
    client = MagicMock()
    client.run_task.return_value = RunTaskResponse(run_id="run-task-1", status="queued")
    client.run_workflow.return_value = _run_out("run-wf-1")
    client.get_run.return_value = _replay("run-1", "completed")
    client.list_runs.return_value = RunListPage(items=[], next_cursor=None)
    client.cancel_run.return_value = _run_out("run-1", "aborted")
    return client


@pytest.fixture(autouse=True)
def _env_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_AGENT_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("AUTO_AGENT_API_KEY", "sk_test_key")


def test_build_parser_requires_subcommand() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_parser_run_task_args() -> None:
    args = build_parser().parse_args(["run-task", "extract title", "--url", "https://example.com", "--watch"])
    assert args.command == "run-task"
    assert args.prompt == "extract title"
    assert args.url == "https://example.com"
    assert args.watch is True


def test_parser_run_workflow_args() -> None:
    args = build_parser().parse_args(
        ["run-workflow", "wf-1", "--parameters", '{"x": 1}', "--json"]
    )
    assert args.command == "run-workflow"
    assert args.workflow_id == "wf-1"
    assert args.parameters == '{"x": 1}'
    assert args.as_json is True


def test_parser_get_run_args() -> None:
    args = build_parser().parse_args(["get-run", "run-1", "--watch"])
    assert args.command == "get-run"
    assert args.run_id == "run-1"
    assert args.watch is True


def test_parser_list_runs_args() -> None:
    args = build_parser().parse_args(["list-runs", "--workflow-id", "wf-1", "--limit", "10"])
    assert args.command == "list-runs"
    assert args.workflow_id == "wf-1"
    assert args.limit == 10


def test_parser_cancel_run_args() -> None:
    args = build_parser().parse_args(["cancel-run", "run-1"])
    assert args.command == "cancel-run"
    assert args.run_id == "run-1"


def test_run_command_run_task(capsys: pytest.CaptureFixture[str]) -> None:
    client = _mock_client()
    args = build_parser().parse_args(["run-task", "hello", "--url", "https://example.com"])
    assert run_command(args, client) == 0
    client.run_task.assert_called_once_with("hello", url="https://example.com", max_steps=8)
    out = capsys.readouterr().out
    assert "run-task-1" in out


def test_run_command_run_workflow(capsys: pytest.CaptureFixture[str]) -> None:
    client = _mock_client()
    args = build_parser().parse_args(["run-workflow", "wf-1", "--parameters", '{"a": 1}'])
    assert run_command(args, client) == 0
    client.run_workflow.assert_called_once_with(
        "wf-1",
        parameters={"a": 1},
        browser_profile_id=None,
        totp_identifier=None,
    )
    assert "run-wf-1" in capsys.readouterr().out


def test_run_command_get_run(capsys: pytest.CaptureFixture[str]) -> None:
    client = _mock_client()
    args = build_parser().parse_args(["get-run", "run-1"])
    assert run_command(args, client) == 0
    client.get_run.assert_called_once_with("run-1")
    assert "completed" in capsys.readouterr().out


def test_run_command_list_runs(capsys: pytest.CaptureFixture[str]) -> None:
    client = _mock_client()
    client.list_runs.return_value = RunListPage(
        items=[
            {
                "id": "run-1",
                "workflow_id": "wf-1",
                "workflow_name": "demo",
                "workflow_version_id": "wv-1",
                "version_index": 1,
                "status": "completed",
                "queued_at": _utcnow(),
                "started_at": _utcnow(),
                "finished_at": _utcnow(),
                "duration_ms": 100,
                "error_summary": None,
                "pending_approval": None,
                "queue_position": None,
            }
        ],
        next_cursor=None,
    )
    args = build_parser().parse_args(["list-runs", "--workflow-id", "wf-1"])
    assert run_command(args, client) == 0
    client.list_runs.assert_called_once_with(workflow_id="wf-1", limit=50, cursor=None)
    assert "run-1" in capsys.readouterr().out


def test_run_command_cancel_run(capsys: pytest.CaptureFixture[str]) -> None:
    client = _mock_client()
    args = build_parser().parse_args(["cancel-run", "run-1"])
    assert run_command(args, client) == 0
    client.cancel_run.assert_called_once_with("run-1")
    assert "aborted" in capsys.readouterr().out


def test_run_command_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    client = _mock_client()
    args = build_parser().parse_args(["get-run", "run-1", "--json"])
    assert run_command(args, client) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run"]["id"] == "run-1"


def test_main_missing_config(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("AUTO_AGENT_BASE_URL", raising=False)
    monkeypatch.delenv("AUTO_AGENT_API_KEY", raising=False)
    code = main(["list-runs"], client=_mock_client())
    assert code == 1
    assert "AUTO_AGENT_BASE_URL" in capsys.readouterr().err


def test_main_with_injected_client(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["cancel-run", "run-1"], client=_mock_client())
    assert code == 0
    assert "aborted" in capsys.readouterr().out


def test_load_config_requires_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTO_AGENT_BASE_URL", raising=False)
    monkeypatch.delenv("AUTO_AGENT_API_KEY", raising=False)
    with pytest.raises(ConfigError) as exc:
        load_config()
    msg = str(exc.value)
    assert "AUTO_AGENT_BASE_URL" in msg
    assert "AUTO_AGENT_API_KEY" in msg


def test_load_config_from_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTO_AGENT_BASE_URL", raising=False)
    monkeypatch.delenv("AUTO_AGENT_API_KEY", raising=False)
    config_file = tmp_path / "config"
    config_file.write_text(
        "base_url = http://127.0.0.1:9000\napi_key = sk_from_file\n",
        encoding="utf-8",
    )
    config_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
    cfg = load_config(config_path=config_file)
    assert cfg.base_url == "http://127.0.0.1:9000"
    assert cfg.api_key == "sk_from_file"


def test_load_config_rejects_world_readable_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if sys.platform == "win32":
        pytest.skip("POSIX permission checks only")
    monkeypatch.delenv("AUTO_AGENT_BASE_URL", raising=False)
    monkeypatch.delenv("AUTO_AGENT_API_KEY", raising=False)
    config_file = tmp_path / "config"
    config_file.write_text("api_key = sk_secret\nbase_url = http://localhost\n", encoding="utf-8")
    config_file.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)
    with pytest.raises(ConfigError, match="0600"):
        load_config(config_path=config_file)


def test_watch_polls_until_terminal(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = _mock_client()
    statuses = iter(["queued", "running", "completed"])

    def next_replay(_run_id: str) -> RunReplayResponse:
        return _replay("run-1", next(statuses))

    client.get_run.side_effect = next_replay
    sleeps: list[float] = []
    monkeypatch.setattr("auto_agent_sdk.cli.time.sleep", lambda s: sleeps.append(s))
    args = build_parser().parse_args(["get-run", "run-1", "--watch"])
    assert run_command(args, client) == 0
    err = capsys.readouterr().err
    assert "Watching run run-1" in err
    assert err.count("status:") == 3
    assert len(sleeps) == 2
