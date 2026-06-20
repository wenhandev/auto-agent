from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Sequence

from auto_agent_sdk.client import AutoAgent
from auto_agent_sdk.config import CliConfig, ConfigError, load_config
from auto_agent_sdk.models import TERMINAL_RUN_STATUSES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="auto-agent", description="CLI for the auto-agent API.")
    parser.add_argument(
        "--base-url",
        dest="base_url",
        help="API base URL (default: AUTO_AGENT_BASE_URL env or config file)",
    )
    parser.add_argument(
        "--api-key",
        dest="api_key",
        help="API key (default: AUTO_AGENT_API_KEY env or config file; never printed)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_task = subparsers.add_parser("run-task", help="Start an ephemeral vision task")
    run_task.add_argument("prompt", help="Task prompt")
    run_task.add_argument("--url", help="Starting URL")
    run_task.add_argument("--max-steps", type=int, default=8, help="Maximum agent steps")
    run_task.add_argument("--watch", action="store_true", help="Poll until terminal status")
    run_task.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON output")

    run_workflow = subparsers.add_parser("run-workflow", help="Enqueue a workflow run")
    run_workflow.add_argument("workflow_id", help="Workflow ID")
    run_workflow.add_argument(
        "--parameters",
        help="Workflow parameters as a JSON object",
    )
    run_workflow.add_argument("--browser-profile-id", help="Browser profile ID")
    run_workflow.add_argument("--totp-identifier", help="TOTP credential identifier")
    run_workflow.add_argument("--watch", action="store_true", help="Poll until terminal status")
    run_workflow.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON output")

    get_run = subparsers.add_parser("get-run", help="Fetch run status and replay data")
    get_run.add_argument("run_id", help="Run ID")
    get_run.add_argument("--watch", action="store_true", help="Poll until terminal status")
    get_run.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON output")

    list_runs = subparsers.add_parser("list-runs", help="List recent runs")
    list_runs.add_argument("--workflow-id", help="Filter by workflow ID")
    list_runs.add_argument("--limit", type=int, default=50, help="Page size")
    list_runs.add_argument("--cursor", help="Pagination cursor")
    list_runs.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON output")

    cancel_run = subparsers.add_parser("cancel-run", help="Cancel a queued or running run")
    cancel_run.add_argument("run_id", help="Run ID")
    cancel_run.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON output")

    return parser


def _emit(payload: Any, *, as_json: bool) -> None:
    if as_json:
        if hasattr(payload, "model_dump"):
            print(json.dumps(payload.model_dump(), indent=2, default=str))
        else:
            print(json.dumps(payload, indent=2, default=str))
        return
    if hasattr(payload, "model_dump"):
        data = payload.model_dump()
        if "run_id" in data:
            print(f"run_id: {data['run_id']}")
            print(f"status: {data['status']}")
            return
        if "id" in data and "status" in data:
            print(f"id: {data['id']}")
            print(f"status: {data['status']}")
            return
        if "items" in data:
            for item in data["items"]:
                print(
                    f"{item['id']}\t{item['status']}\t{item.get('workflow_name', item.get('workflow_id', ''))}"
                )
            if data.get("next_cursor"):
                print(f"next_cursor: {data['next_cursor']}", file=sys.stderr)
            return
        run = data.get("run")
        if run:
            print(f"id: {run['id']}")
            print(f"status: {run['status']}")
            if run.get("error"):
                print(f"error: {run['error']}")
            return
    print(payload)


def _watch_status(
    client: AutoAgent,
    run_id: str,
    *,
    poll_interval: float = 1.0,
    max_interval: float = 5.0,
) -> Any:
    print(f"Watching run {run_id}...", file=sys.stderr)
    interval = poll_interval
    while True:
        replay = client.get_run(run_id)
        print(f"status: {replay.run.status}", file=sys.stderr)
        if replay.run.error:
            print(f"error: {replay.run.error}", file=sys.stderr)
        if replay.run.status in TERMINAL_RUN_STATUSES:
            return replay
        time.sleep(interval)
        interval = min(interval * 1.5, max_interval)


def run_command(args: argparse.Namespace, client: AutoAgent) -> int:
    if args.command == "run-task":
        result = client.run_task(
            args.prompt,
            url=args.url,
            max_steps=args.max_steps,
        )
        if args.watch:
            result = _watch_status(client, result.run_id)
        _emit(result, as_json=args.as_json)
        return 0

    if args.command == "run-workflow":
        parameters = json.loads(args.parameters) if args.parameters else None
        result = client.run_workflow(
            args.workflow_id,
            parameters=parameters,
            browser_profile_id=args.browser_profile_id,
            totp_identifier=args.totp_identifier,
        )
        if args.watch:
            result = _watch_status(client, result.id)
        _emit(result, as_json=args.as_json)
        return 0

    if args.command == "get-run":
        if args.watch:
            result = _watch_status(client, args.run_id)
        else:
            result = client.get_run(args.run_id)
        _emit(result, as_json=args.as_json)
        return 0

    if args.command == "list-runs":
        result = client.list_runs(
            workflow_id=args.workflow_id,
            limit=args.limit,
            cursor=args.cursor,
        )
        _emit(result, as_json=args.as_json)
        return 0

    if args.command == "cancel-run":
        result = client.cancel_run(args.run_id)
        _emit(result, as_json=args.as_json)
        return 0

    raise SystemExit(f"Unknown command: {args.command}")


def main(argv: Sequence[str] | None = None, *, client: AutoAgent | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        config: CliConfig = load_config(base_url=args.base_url, api_key=args.api_key)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    sdk = client or AutoAgent(config.base_url, config.api_key)
    return run_command(args, sdk)


def entrypoint() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
