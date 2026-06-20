"""Selector cache learning: hit/miss, normalisation, invalidation."""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from sqlmodel import Session

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app import executor
from app.db.models import SelectorCache, Workflow, WorkflowVersion
from app.db.session import engine
from app.main import app
from app.schemas import Node
from app.services import llm_runtime
from app.services import selector_cache as cache_svc


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _LocatorStub:
    def __init__(self, page: "_StubPage", selector: str) -> None:
        self._page = page
        self._selector = selector

    async def click(self, timeout: int | None = None) -> None:
        await self._page._click(self._selector)

    async def fill(self, value: str, timeout: int | None = None) -> None:
        await self._page._fill(self._selector, value)


class _StubPage:
    def __init__(self, url: str) -> None:
        self.url = url
        self.click_calls: list[str] = []
        self.fill_calls: list[tuple[str, str]] = []

    def locator(self, selector: str) -> _LocatorStub:
        return _LocatorStub(self, selector)

    async def _click(self, selector: str) -> None:
        self.click_calls.append(selector)
        if selector == "#stale":
            raise PlaywrightTimeoutError("waiting for selector")

    async def _fill(self, selector: str, value: str) -> None:
        self.fill_calls.append((selector, value))
        if selector == "#stale":
            raise PlaywrightTimeoutError("waiting for selector")

    async def screenshot(self, **_: Any) -> bytes:
        return b""

    @property
    def accessibility(self) -> Any:
        class _Ax:
            async def snapshot(self_inner) -> dict:  # noqa: N805
                return {"role": "WebArea"}

        return _Ax()


async def _capture_emit() -> tuple[Any, list[dict]]:
    events: list[dict] = []

    async def emit(event: str, *, node_id: str | None = None, **extra: Any) -> None:
        payload = {"event": event, "node_id": node_id}
        payload.update(extra)
        events.append(payload)

    return emit, events


def _patch_cache_settings(monkeypatch: pytest.MonkeyPatch, *, enabled: bool = True) -> None:
    monkeypatch.setattr(
        llm_runtime,
        "get_selector_cache_settings",
        lambda session=None: llm_runtime.SelectorCacheSettings(enabled=enabled),
    )
    monkeypatch.setattr(
        llm_runtime,
        "get_self_heal_settings",
        lambda session=None: llm_runtime.SelfHealSettings(enabled=True, threshold=0.6),
    )


@pytest.fixture
def workflow_id() -> str:
    wf_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    with Session(engine) as session:
        session.add(
            Workflow(
                id=wf_id,
                name="cache-test",
                current_version_id=version_id,
            )
        )
        session.add(
            WorkflowVersion(
                id=version_id,
                workflow_id=wf_id,
                version_index=1,
                nodes_json="[]",
                edges_json="[]",
                start_id="start",
                authored_by="manual",
            )
        )
        session.commit()
    return wf_id


def test_normalize_url_groups_numeric_paths() -> None:
    a = cache_svc.normalize_url("https://shop.example/product/123?utm_source=x")
    b = cache_svc.normalize_url("https://shop.example/product/456?ref=home")
    assert a == b
    assert "/product/{id}" in a
    assert "utm_source" not in a
    assert "ref" not in a


def test_normalize_url_strict_mode() -> None:
    url = "https://shop.example/product/123?ref=1"
    assert cache_svc.normalize_url(url, {"cache_url_normalizer": "strict"}) == url


@pytest.mark.asyncio
async def test_cache_hit_skips_llm(
    monkeypatch: pytest.MonkeyPatch, workflow_id: str
) -> None:
    page = _StubPage("https://shop.example/product/99")

    async def _get_page() -> _StubPage:
        return page

    monkeypatch.setattr("app.executor.get_page", _get_page)
    monkeypatch.setattr("app.tools.browser.get_page", _get_page)
    _patch_cache_settings(monkeypatch)

    propose_calls: list[str] = []

    async def fake_propose(*, page, instruction, mode):
        propose_calls.append(mode)
        return {"selector": "#never", "confidence": 0.9, "reasoning": "", "cost_hint": {}}

    monkeypatch.setattr("app.agents.selector_finder.propose_selector", fake_propose)

    async def fake_click(selector: str) -> dict:
        if selector == "#wrong":
            raise PlaywrightTimeoutError("waiting for selector")
        return {"selector": selector, "clicked": True}

    monkeypatch.setattr("app.tools.actions.click", fake_click)

    with Session(engine) as session:
        cache_svc.upsert_success(
            session,
            workflow_id=workflow_id,
            node_id="n-hit",
            url=page.url,
            selector="#cached",
            confidence=0.95,
        )

        emit, events = await _capture_emit()
        node = Node(id="n-hit", type="click", label="hit", params={"selector": "#wrong"})
        result = await executor._run_node(
            node, emit, session=session, workflow_id=workflow_id
        )

    assert result == {"selector": "#cached", "clicked": True}
    assert propose_calls == []
    assert page.click_calls == ["#cached"]
    hits = [e for e in events if e["event"] == "cache_hit"]
    assert len(hits) == 1
    assert hits[0]["selector"] == "#cached"


@pytest.mark.asyncio
async def test_cache_miss_when_cached_selector_differs_from_node_params(
    monkeypatch: pytest.MonkeyPatch, workflow_id: str
) -> None:
    page = _StubPage("https://shop.example/support/1")

    async def _get_page() -> _StubPage:
        return page

    monkeypatch.setattr("app.executor.get_page", _get_page)
    monkeypatch.setattr("app.tools.browser.get_page", _get_page)
    _patch_cache_settings(monkeypatch)

    async def fake_fill(selector: str, value: str) -> dict:
        return {"selector": selector, "value": value}

    monkeypatch.setattr("app.tools.actions.fill", fake_fill)

    with Session(engine) as session:
        cache_svc.upsert_success(
            session,
            workflow_id=workflow_id,
            node_id="n-subject",
            url=page.url,
            selector="#description",
            confidence=0.95,
        )

        emit, events = await _capture_emit()
        node = Node(
            id="n-subject",
            type="fill",
            label="subject",
            params={"selector": "#subject", "value": "hello", "auto_heal": False},
        )
        result = await executor._run_node(
            node, emit, session=session, workflow_id=workflow_id
        )

    assert result == {"selector": "#subject", "value": "hello"}
    misses = [e for e in events if e["event"] == "cache_miss"]
    assert any(m["reason"] == "selector_mismatch" for m in misses)
    hits = [e for e in events if e["event"] == "cache_hit"]
    assert hits == []


@pytest.mark.asyncio
async def test_cache_miss_falls_back_and_heal_updates(
    monkeypatch: pytest.MonkeyPatch, workflow_id: str
) -> None:
    page = _StubPage("https://shop.example/checkout/1")

    async def _get_page() -> _StubPage:
        return page

    monkeypatch.setattr("app.executor.get_page", _get_page)
    monkeypatch.setattr("app.tools.browser.get_page", _get_page)
    _patch_cache_settings(monkeypatch)

    async def fake_click(selector: str) -> dict:
        if selector == "#wrong":
            raise PlaywrightTimeoutError("waiting for selector")
        return {"selector": selector, "clicked": True}

    monkeypatch.setattr("app.tools.actions.click", fake_click)

    async def fake_propose(*, page, instruction, mode):
        return {
            "selector": "#healed",
            "confidence": 0.88,
            "reasoning": "ok",
            "cost_hint": {"input_tokens": 10, "output_tokens": 2, "vision_calls": 0},
        }

    monkeypatch.setattr("app.agents.selector_finder.propose_selector", fake_propose)

    with Session(engine) as session:
        emit, events = await _capture_emit()
        node = Node(id="n-miss", type="click", label="miss", params={"selector": "#wrong"})
        result = await executor._run_node(
            node, emit, session=session, workflow_id=workflow_id
        )

    assert result == {"selector": "#healed", "clicked": True}
    misses = [e for e in events if e["event"] == "cache_miss"]
    assert any(m["reason"] == "no_entry" for m in misses)

    with Session(engine) as session:
        lookup = cache_svc.get_entry(
            session,
            workflow_id=workflow_id,
            node_id="n-miss",
            url=page.url,
        )
        assert lookup is not None
        assert lookup.entry.selector == "#healed"
        assert lookup.entry.confidence == pytest.approx(0.88)


def test_invalidation_after_consecutive_misses(workflow_id: str) -> None:
    with Session(engine) as session:
        entry = cache_svc.upsert_success(
            session,
            workflow_id=workflow_id,
            node_id="n-evict",
            url="https://example.com/page/1",
            selector="#old",
            confidence=1.0,
        )
        entry_id = entry.id
        evicted = False
        for _ in range(3):
            row = session.get(SelectorCache, entry_id)
            assert row is not None
            evicted = cache_svc.record_miss(session, row)
            if evicted:
                break
        assert evicted is True
        assert session.get(SelectorCache, entry_id) is None


def test_ttl_eviction(workflow_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.settings.settings.cache_ttl_days", 7)

    with Session(engine) as session:
        entry = cache_svc.upsert_success(
            session,
            workflow_id=workflow_id,
            node_id="n-ttl",
            url="https://example.com/old/1",
            selector="#btn",
            confidence=1.0,
        )
        entry.last_success_at = _utcnow() - timedelta(days=10)
        session.add(entry)
        session.commit()

        lookup = cache_svc.get_entry(
            session,
            workflow_id=workflow_id,
            node_id="n-ttl",
            url="https://example.com/old/99",
        )
        assert lookup is None


def test_api_cache_stats_and_clear(workflow_id: str) -> None:
    client = TestClient(app)
    with Session(engine) as session:
        cache_svc.upsert_success(
            session,
            workflow_id=workflow_id,
            node_id="api-node",
            url="https://example.com/a/1",
            selector="#x",
            confidence=1.0,
        )
        entry = cache_svc.get_entry(
            session,
            workflow_id=workflow_id,
            node_id="api-node",
            url="https://example.com/a/1",
        )
        assert entry is not None
        cache_svc.record_hit(session, entry.entry)

    stats = client.get(f"/api/workflows/{workflow_id}/selector-cache")
    assert stats.status_code == 200
    body = stats.json()
    assert body["entry_count"] == 1
    assert body["total_hits"] == 1

    cleared = client.delete(f"/api/workflows/{workflow_id}/selector-cache")
    assert cleared.status_code == 200
    assert cleared.json()["removed"] == 1

    stats2 = client.get(f"/api/workflows/{workflow_id}/selector-cache")
    assert stats2.json()["entry_count"] == 0
