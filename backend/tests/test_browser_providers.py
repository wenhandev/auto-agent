"""Browser provider runtime: local Playwright default, remote CDP, capability checks."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.models import BrowserSession, Workflow, WorkflowVersion
from app.db.session import engine, init_db
from app.main import app
from app.services import browser_pool
from app.services import browser_sessions as session_svc
from app.services.browser_providers import (
    BrowserProviderConfig,
    UnsupportedBrowserCapabilityError,
    default_provider_config,
    get_provider,
    require_capability,
    sanitize_provider_metadata,
)


class _FakePage:
    is_closed = False

    def __init__(self, context: object) -> None:
        self.context = context


class _FakeContext:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    async def close(self) -> None:
        pass

    async def new_page(self) -> _FakePage:
        return _FakePage(self)


class _FakeBrowser:
    contexts: list = []

    def is_connected(self) -> bool:
        return True

    async def new_context(self, **kwargs) -> _FakeContext:
        ctx = _FakeContext(**kwargs)
        self.contexts = [ctx]
        return ctx

    async def close(self) -> None:
        pass


@pytest.fixture()
def mock_browser(monkeypatch: pytest.MonkeyPatch):
    fake = _FakeBrowser()
    monkeypatch.setattr(browser_pool, "_browser", fake)
    monkeypatch.setattr(browser_pool, "_playwright", MagicMock())
    browser_pool.reset_for_tests()
    session_svc.reset_for_tests()
    yield fake
    browser_pool.reset_for_tests()
    session_svc.reset_for_tests()


def test_default_provider_is_local_playwright() -> None:
    cfg = default_provider_config()
    provider = get_provider(cfg)
    assert provider.provider_id == "local_playwright"
    assert "persistent_context" in provider.capabilities


def test_local_playwright_capabilities_include_captcha_and_computer_use() -> None:
    provider = get_provider(default_provider_config())
    for cap in ("captcha", "computer_use", "recording", "live_view", "proxy"):
        require_capability(provider, cap)


def test_unsupported_capability_raises_clearly() -> None:
    provider = get_provider(
        BrowserProviderConfig(provider_id="remote_cdp", config={"endpoint_url": "ws://x"})
    )
    with pytest.raises(UnsupportedBrowserCapabilityError, match="persistent_context"):
        require_capability(provider, "persistent_context")


def test_sanitize_metadata_strips_secrets() -> None:
    raw = {
        "endpoint_url": "wss://browser.example/devtools",
        "token": "secret-token",
        "password": "secret-password",
        "api_key": "secret-key",
    }
    safe = sanitize_provider_metadata(raw)
    assert safe["endpoint_url"] == "wss://browser.example/devtools"
    assert "token" not in safe
    assert "password" not in safe
    assert "api_key" not in safe
    assert safe.get("has_token") is True


@pytest.mark.asyncio
async def test_local_playwright_context_creation_unchanged(mock_browser) -> None:
    from app.services.browser_providers import create_browser_connection

    conn = await create_browser_connection("run-test", profile_id=None)
    assert conn.context is not None
    assert conn.page is not None
    assert conn.provider_id == "local_playwright"
    await browser_pool.close_context_entry(conn.context, conn.page)


@pytest.mark.asyncio
async def test_remote_cdp_connects_with_endpoint(mock_browser, monkeypatch) -> None:
    from app.services import browser_providers as prov_mod

    fake_browser = _FakeBrowser()
    connect = AsyncMock(return_value=fake_browser)
    monkeypatch.setattr(prov_mod, "_connect_over_cdp", connect)

    cfg = BrowserProviderConfig(
        provider_id="remote_cdp",
        config={"endpoint_url": "wss://remote.example/cdp", "token": "secret"},
    )
    conn = await prov_mod.create_browser_connection("sess-remote", profile_id=None, config=cfg)
    connect.assert_awaited_once()
    assert conn.provider_id == "remote_cdp"
    assert conn.metadata.get("endpoint_url") == "wss://remote.example/cdp"
    assert "token" not in conn.metadata
    await browser_pool.close_context_entry(conn.context, conn.page)


@pytest.mark.asyncio
async def test_create_session_persists_provider_metadata(mock_browser) -> None:
    with Session(engine) as db:
        row = await session_svc.create_session(
            db,
            provider_id="local_playwright",
        )
        assert row.provider_id == "local_playwright"
        assert row.provider_metadata_json is not None


@pytest.mark.asyncio
async def test_remote_cdp_session_api_hides_secrets(mock_browser, monkeypatch) -> None:
    from app.services import browser_providers as prov_mod

    fake_browser = _FakeBrowser()
    monkeypatch.setattr(prov_mod, "_connect_over_cdp", AsyncMock(return_value=fake_browser))

    client = TestClient(app)
    resp = client.post(
        "/api/browser-sessions",
        json={
            "provider_id": "remote_cdp",
            "provider_config": {
                "endpoint_url": "wss://remote.example/cdp",
                "token": "super-secret",
            },
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider_id"] == "remote_cdp"
    meta = body.get("provider_metadata") or {}
    assert meta.get("endpoint_url") == "wss://remote.example/cdp"
    assert "token" not in meta
    assert "super-secret" not in str(body)


def _seed_workflow(db: Session) -> str:
    wf = Workflow(name=f"wf-{uuid.uuid4().hex[:8]}")
    db.add(wf)
    db.commit()
    db.refresh(wf)
    ver = WorkflowVersion(
        workflow_id=wf.id,
        version_index=1,
        nodes_json="[]",
        edges_json="[]",
        start_id="start",
        authored_by="manual",
    )
    db.add(ver)
    wf.current_version_id = ver.id
    db.add(wf)
    db.commit()
    return wf.id


@pytest.mark.asyncio
async def test_run_inherits_session_provider_metadata(mock_browser) -> None:
    from app.services import runs as run_svc

    with Session(engine) as db:
        session_row = await session_svc.create_session(
            db,
            provider_id="local_playwright",
        )
        wf_id = _seed_workflow(db)
        wf = db.get(Workflow, wf_id)
        assert wf is not None
        run = run_svc.enqueue_run(
            wf_id,
            db,
            version_id=wf.current_version_id,
            browser_session_id=session_row.id,
        )
        assert run.browser_provider_id == "local_playwright"
        assert run.browser_provider_metadata_json is not None
