"""Self-heal flow tests.

These tests exercise ``app.executor._run_node`` for the click/fill path
without actually calling Playwright. We monkeypatch
``app.tools.actions.click`` / ``.fill`` and the heal-stage
``app.agents.selector_finder.propose_selector`` so the flow is fully
deterministic in-process.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app import executor
from app.schemas import Node
from app.services import llm_runtime


@pytest.fixture(autouse=True)
def _headless_for_self_heal_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.settings.settings.browser_headless", True)


class _StubPage:
    async def screenshot(self, **_: Any) -> bytes:
        return b""

    @property
    def accessibility(self) -> Any:
        page = self

        class _Ax:
            async def snapshot(self_inner) -> dict:  # noqa: N805 - mirroring Playwright API
                return {"role": "WebArea"}

        return _Ax()


async def _capture_emit() -> tuple[Any, list[dict]]:
    events: list[dict] = []

    async def emit(event: str, *, node_id: str | None = None, **extra: Any) -> None:
        payload = {"event": event, "node_id": node_id}
        payload.update(extra)
        events.append(payload)

    return emit, events


def _install_browser_stub(monkeypatch: pytest.MonkeyPatch) -> _StubPage:
    page = _StubPage()

    async def _get_page() -> _StubPage:
        return page

    monkeypatch.setattr("app.executor.get_page", _get_page)
    monkeypatch.setattr("app.tools.browser.get_page", _get_page)
    return page


def _patch_settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    enabled: bool = True,
    threshold: float = 0.6,
) -> None:
    monkeypatch.setattr(
        llm_runtime,
        "get_self_heal_settings",
        lambda session=None: llm_runtime.SelfHealSettings(
            enabled=enabled, threshold=threshold
        ),
    )


@pytest.mark.asyncio
async def test_dom_only_heal_sufficient(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_browser_stub(monkeypatch)
    _patch_settings(monkeypatch, enabled=True, threshold=0.6)

    click_calls: list[str] = []

    async def fake_click(selector: str) -> dict:
        click_calls.append(selector)
        if selector == "#wrong":
            raise PlaywrightTimeoutError(
                "Timeout 30000ms exceeded.\nwaiting for selector \"#wrong\""
            )
        return {"selector": selector, "clicked": True}

    monkeypatch.setattr("app.tools.actions.click", fake_click)

    async def fake_propose(*, page, instruction, mode):
        assert mode == "dom"
        return {
            "selector": "#real",
            "confidence": 0.85,
            "reasoning": "stable id",
            "cost_hint": {
                "input_tokens": 100,
                "output_tokens": 5,
                "vision_calls": 0,
            },
        }

    monkeypatch.setattr(
        "app.agents.selector_finder.propose_selector", fake_propose
    )

    emit, events = await _capture_emit()
    node = Node(id="n1", type="click", label="login button", params={"selector": "#wrong"})

    result = await executor._run_node(node, emit, session=None)

    assert result == {"selector": "#real", "clicked": True}
    assert click_calls == ["#wrong", "#real"]
    heal_events = [e for e in events if e["event"] == "node_self_healed"]
    assert len(heal_events) == 1
    payload = heal_events[0]
    assert payload["mode"] == "dom"
    assert payload["old_selector"] == "#wrong"
    assert payload["new_selector"] == "#real"
    assert payload["confidence"] == pytest.approx(0.85)
    assert payload["cost_hint"]["vision_calls"] == 0


@pytest.mark.asyncio
async def test_dom_low_then_vision_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_browser_stub(monkeypatch)
    _patch_settings(monkeypatch, enabled=True, threshold=0.6)

    click_calls: list[str] = []

    async def fake_click(selector: str) -> dict:
        click_calls.append(selector)
        if selector == "#wrong":
            raise PlaywrightTimeoutError("waiting for selector \"#wrong\"")
        return {"selector": selector, "clicked": True}

    monkeypatch.setattr("app.tools.actions.click", fake_click)

    calls: list[str] = []

    async def fake_propose(*, page, instruction, mode):
        calls.append(mode)
        if mode == "dom":
            return {
                "selector": "#maybe",
                "confidence": 0.3,
                "reasoning": "low confidence",
                "cost_hint": {
                    "input_tokens": 50,
                    "output_tokens": 4,
                    "vision_calls": 0,
                },
            }
        return {
            "selector": "#real",
            "confidence": 0.9,
            "reasoning": "screenshot confirms",
            "cost_hint": {
                "input_tokens": 200,
                "output_tokens": 10,
                "vision_calls": 1,
            },
        }

    monkeypatch.setattr(
        "app.agents.selector_finder.propose_selector", fake_propose
    )

    emit, events = await _capture_emit()
    node = Node(id="n2", type="click", label="submit", params={"selector": "#wrong"})

    result = await executor._run_node(node, emit, session=None)

    assert result == {"selector": "#real", "clicked": True}
    assert calls == ["dom", "vision"]
    heal_events = [e for e in events if e["event"] == "node_self_healed"]
    assert len(heal_events) == 1
    payload = heal_events[0]
    assert payload["mode"] == "vision"
    assert payload["new_selector"] == "#real"
    assert payload["confidence"] == pytest.approx(0.9)
    assert payload["cost_hint"]["vision_calls"] == 1
    assert payload["cost_hint"]["input_tokens"] == 250
    assert payload["cost_hint"]["output_tokens"] == 14


@pytest.mark.asyncio
async def test_both_stages_fail_raises_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_browser_stub(monkeypatch)
    _patch_settings(monkeypatch, enabled=True, threshold=0.6)

    async def fake_click(selector: str) -> dict:
        raise PlaywrightTimeoutError(
            "Timeout 30000ms exceeded.\nwaiting for selector \"#wrong\""
        )

    monkeypatch.setattr("app.tools.actions.click", fake_click)

    async def fake_propose(*, page, instruction, mode):
        return {
            "selector": None,
            "confidence": 0.0,
            "reasoning": "no candidate",
            "cost_hint": {
                "input_tokens": None,
                "output_tokens": None,
                "vision_calls": 1 if mode == "vision" else 0,
            },
        }

    monkeypatch.setattr(
        "app.agents.selector_finder.propose_selector", fake_propose
    )

    emit, events = await _capture_emit()
    node = Node(id="n3", type="click", label="submit", params={"selector": "#wrong"})

    with pytest.raises(PlaywrightTimeoutError):
        await executor._run_node(node, emit, session=None)

    heal_events = [e for e in events if e["event"] == "node_self_healed"]
    assert len(heal_events) == 1
    payload = heal_events[0]
    assert payload["mode"] == "vision"
    assert payload["new_selector"] is None
    assert payload["confidence"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_auto_heal_false_skips_heal(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_browser_stub(monkeypatch)
    _patch_settings(monkeypatch, enabled=True, threshold=0.6)

    async def fake_click(selector: str) -> dict:
        raise PlaywrightTimeoutError(
            "Timeout 30000ms exceeded.\nwaiting for selector \"#wrong\""
        )

    monkeypatch.setattr("app.tools.actions.click", fake_click)

    propose_calls: list[str] = []

    async def fake_propose(*, page, instruction, mode):
        propose_calls.append(mode)
        return {
            "selector": "#real",
            "confidence": 0.9,
            "reasoning": "should never be called",
            "cost_hint": {"input_tokens": None, "output_tokens": None, "vision_calls": 0},
        }

    monkeypatch.setattr(
        "app.agents.selector_finder.propose_selector", fake_propose
    )

    emit, events = await _capture_emit()
    node = Node(
        id="n4",
        type="click",
        label="submit",
        params={"selector": "#wrong", "auto_heal": False},
    )

    with pytest.raises(PlaywrightTimeoutError):
        await executor._run_node(node, emit, session=None)

    assert propose_calls == []
    assert not any(e["event"] == "node_self_healed" for e in events)


@pytest.mark.asyncio
async def test_global_disabled_skips_heal(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_browser_stub(monkeypatch)
    _patch_settings(monkeypatch, enabled=False, threshold=0.6)

    async def fake_click(selector: str) -> dict:
        raise PlaywrightTimeoutError("waiting for selector \"#wrong\"")

    monkeypatch.setattr("app.tools.actions.click", fake_click)

    propose_calls: list[str] = []

    async def fake_propose(*, page, instruction, mode):
        propose_calls.append(mode)
        return {"selector": None, "confidence": 0.0, "reasoning": "", "cost_hint": {}}

    monkeypatch.setattr(
        "app.agents.selector_finder.propose_selector", fake_propose
    )

    emit, events = await _capture_emit()
    node = Node(id="n5", type="click", label="submit", params={"selector": "#wrong"})

    with pytest.raises(PlaywrightTimeoutError):
        await executor._run_node(node, emit, session=None)

    assert propose_calls == []
    assert not any(e["event"] == "node_self_healed" for e in events)


@pytest.mark.asyncio
async def test_threshold_zero_uses_dom_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_browser_stub(monkeypatch)
    _patch_settings(monkeypatch, enabled=True, threshold=0.0)

    async def fake_click(selector: str) -> dict:
        if selector == "#wrong":
            raise PlaywrightTimeoutError("waiting for selector \"#wrong\"")
        return {"selector": selector, "clicked": True}

    monkeypatch.setattr("app.tools.actions.click", fake_click)

    calls: list[str] = []

    async def fake_propose(*, page, instruction, mode):
        calls.append(mode)
        return {
            "selector": "#real",
            "confidence": 0.55,
            "reasoning": "modest",
            "cost_hint": {"input_tokens": 10, "output_tokens": 2, "vision_calls": 0},
        }

    monkeypatch.setattr(
        "app.agents.selector_finder.propose_selector", fake_propose
    )

    emit, events = await _capture_emit()
    node = Node(id="n6", type="click", label="submit", params={"selector": "#wrong"})

    await executor._run_node(node, emit, session=None)

    assert calls == ["dom"]
    healed = [e for e in events if e["event"] == "node_self_healed"][0]
    assert healed["mode"] == "dom"
    assert healed["cost_hint"]["vision_calls"] == 0
