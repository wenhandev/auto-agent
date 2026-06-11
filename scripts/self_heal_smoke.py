"""Self-healing selectors smoke test.

Runs the executor in-process against a tiny in-memory HTTP page that
serves ``<button id="real-btn">Click</button>``. The workflow's click
node intentionally targets ``#wrong-btn`` so the deterministic action
fails; the heal flow then asks a MOCKED ``propose_selector`` (so no
LLM calls are made) and retries with the candidate.

Three scenarios:

  1) DOM stage returns high confidence -> ``mode="dom"`` heal succeeds.
  2) DOM stage returns low confidence -> vision stage returns high
     confidence -> ``mode="vision"`` heal succeeds.
  3) Both stages return ``None`` -> heal emits a failure event and the
     original error surfaces, ``node_failed`` fires.

Run from repo root with the backend's venv active:

    python scripts/self_heal_smoke.py
"""
from __future__ import annotations

import asyncio
import http.server
import os
import socketserver
import sys
import threading
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_BACKEND_ROOT = _REPO_ROOT / "backend"
for p in (_BACKEND_ROOT,):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

os.environ.setdefault("BROWSER_HEADLESS", "true")

from app import executor
from app.schemas import Edge, Node, Workflow
from app.services import llm_runtime
from app.tools import browser as browser_tools


_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>self-heal smoke</title></head>
<body><h1>self-heal smoke</h1>
<button id="real-btn">Click</button>
</body></html>"""


class _Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = _HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: Any) -> None:
        return


def _serve_in_background() -> tuple[str, socketserver.TCPServer, threading.Thread]:
    server = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    server.allow_reuse_address = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return f"http://{host}:{port}/", server, thread


def _make_workflow() -> Workflow:
    return Workflow(
        nodes=[
            Node(id="start", type="start", label="start", params={}),
            Node(id="nav", type="navigate", label="open", params={"url": "PLACEHOLDER"}),
            Node(
                id="click1",
                type="click",
                label="primary button",
                params={"selector": "#wrong-btn"},
            ),
            Node(id="end", type="end", label="end", params={}),
        ],
        edges=[
            Edge(id="e1", source="start", target="nav"),
            Edge(id="e2", source="nav", target="click1"),
            Edge(id="e3", source="click1", target="end"),
        ],
        start_id="start",
    )


def _set_heal(enabled: bool, threshold: float) -> None:
    llm_runtime.invalidate_cache()
    llm_runtime.get_self_heal_settings = (  # type: ignore[assignment]
        lambda session=None: llm_runtime.SelfHealSettings(
            enabled=enabled, threshold=threshold
        )
    )


def _install_mock_propose(behaviour: dict[str, dict]) -> list[str]:
    call_log: list[str] = []

    async def fake_propose(*, page, instruction, mode):
        call_log.append(mode)
        return behaviour[mode]

    import app.agents.selector_finder as sf

    sf.propose_selector = fake_propose  # type: ignore[assignment]
    return call_log


async def _run_case(name: str, url: str, behaviour: dict[str, dict]) -> tuple[bool, list[dict]]:
    print(f"\n=== case: {name} ===")
    call_log = _install_mock_propose(behaviour)

    wf = _make_workflow()
    wf.nodes[1].params["url"] = url

    events: list[dict] = []

    async def emit(payload: dict) -> None:
        events.append(payload)
        ev = payload.get("event")
        nid = payload.get("node_id") or ""
        extra = ""
        if ev == "node_self_healed":
            extra = (
                f" mode={payload.get('mode')!r}"
                f" new={payload.get('new_selector')!r}"
                f" conf={payload.get('confidence')!r}"
            )
        elif ev == "node_failed":
            extra = f" err={payload.get('error')!r}"
        print(f"  [evt] {ev} {nid}{extra}")

    try:
        await executor.run_workflow(wf, emit)
    finally:
        try:
            await browser_tools.shutdown()
        except Exception:
            pass

    print(f"  agent calls: {call_log}")
    return True, events


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        print(f"  ASSERT FAIL: {msg}")
        raise SystemExit(2)
    print(f"  ok: {msg}")


async def main() -> int:
    url, server, _thread = _serve_in_background()
    print(f"local server: {url}")

    try:
        _set_heal(enabled=True, threshold=0.6)

        _, events = await _run_case(
            "dom-stage-sufficient",
            url,
            {
                "dom": {
                    "selector": "#real-btn",
                    "confidence": 0.9,
                    "reasoning": "stable id match",
                    "cost_hint": {
                        "input_tokens": 100,
                        "output_tokens": 5,
                        "vision_calls": 0,
                    },
                },
                "vision": {
                    "selector": None,
                    "confidence": 0.0,
                    "reasoning": "never reached",
                    "cost_hint": {
                        "input_tokens": None,
                        "output_tokens": None,
                        "vision_calls": 1,
                    },
                },
            },
        )
        healed = [e for e in events if e["event"] == "node_self_healed"]
        completed_click = [
            e for e in events
            if e["event"] == "node_completed" and e.get("node_id") == "click1"
        ]
        _assert(len(healed) == 1, "exactly one node_self_healed event")
        _assert(healed[0]["mode"] == "dom", 'heal mode == "dom"')
        _assert(healed[0]["new_selector"] == "#real-btn", "heal carried new selector #real-btn")
        _assert(healed[0]["cost_hint"]["vision_calls"] == 0, "vision_calls == 0")
        _assert(len(completed_click) == 1, "click node completed after heal")

        _, events = await _run_case(
            "dom-low-then-vision",
            url,
            {
                "dom": {
                    "selector": "#maybe",
                    "confidence": 0.3,
                    "reasoning": "low",
                    "cost_hint": {
                        "input_tokens": 50,
                        "output_tokens": 3,
                        "vision_calls": 0,
                    },
                },
                "vision": {
                    "selector": "#real-btn",
                    "confidence": 0.85,
                    "reasoning": "screenshot confirms primary CTA",
                    "cost_hint": {
                        "input_tokens": 200,
                        "output_tokens": 10,
                        "vision_calls": 1,
                    },
                },
            },
        )
        healed = [e for e in events if e["event"] == "node_self_healed"]
        completed_click = [
            e for e in events
            if e["event"] == "node_completed" and e.get("node_id") == "click1"
        ]
        _assert(len(healed) == 1, "exactly one node_self_healed event")
        _assert(healed[0]["mode"] == "vision", 'heal mode == "vision"')
        _assert(healed[0]["new_selector"] == "#real-btn", "heal carried new selector #real-btn")
        _assert(healed[0]["cost_hint"]["vision_calls"] == 1, "vision_calls == 1")
        _assert(
            healed[0]["cost_hint"]["input_tokens"] == 250,
            "aggregated input_tokens == 250",
        )
        _assert(len(completed_click) == 1, "click node completed after vision-stage heal")

        _, events = await _run_case(
            "both-stages-fail",
            url,
            {
                "dom": {
                    "selector": None,
                    "confidence": 0.0,
                    "reasoning": "no candidate",
                    "cost_hint": {
                        "input_tokens": None,
                        "output_tokens": None,
                        "vision_calls": 0,
                    },
                },
                "vision": {
                    "selector": None,
                    "confidence": 0.0,
                    "reasoning": "no candidate from vision either",
                    "cost_hint": {
                        "input_tokens": None,
                        "output_tokens": None,
                        "vision_calls": 1,
                    },
                },
            },
        )
        healed = [e for e in events if e["event"] == "node_self_healed"]
        failed = [
            e for e in events
            if e["event"] == "node_failed" and e.get("node_id") == "click1"
        ]
        _assert(len(healed) == 1, "exactly one node_self_healed event (failure)")
        _assert(healed[0]["mode"] == "vision", 'final mode tag == "vision"')
        _assert(healed[0]["new_selector"] is None, "new_selector is None on failure")
        _assert(len(failed) == 1, "node_failed fired with original Playwright error")

    finally:
        server.shutdown()
        server.server_close()

    print("\nALL ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
