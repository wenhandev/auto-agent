"""Browser live session manager, API, and run wiring tests (mock Playwright)."""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

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
from app.services import browser_profiles as profile_svc
from app.services import browser_sessions as session_svc
from app.settings import settings
from app.tools import browser as browser_tools


def _unique_name(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


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
    def is_connected(self) -> bool:
        return True

    async def new_context(self, **kwargs) -> _FakeContext:
        return _FakeContext(**kwargs)

    async def close(self) -> None:
        pass


@pytest.fixture()
def profiles_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "profiles"
    profile_svc.set_profiles_root(root)
    yield root
    profile_svc.reset_profiles_root()


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


@pytest.fixture()
def client(profiles_tmp: Path, mock_browser: _FakeBrowser) -> TestClient:
    return TestClient(app)


@pytest.fixture()
def seeded_workflow(profiles_tmp: Path) -> str:
    init_db()
    with Session(engine) as session:
        wf = Workflow(name=_unique_name("session-test-wf"))
        session.add(wf)
        session.commit()
        session.refresh(wf)
        version = WorkflowVersion(
            workflow_id=wf.id,
            version_index=1,
            nodes_json="[]",
            edges_json="[]",
            start_id="s",
            authored_by="manual",
        )
        session.add(version)
        session.commit()
        session.refresh(version)
        wf.current_version_id = version.id
        session.add(wf)
        session.commit()
        return wf.id


def test_create_session_returns_live_row(client: TestClient) -> None:
    resp = client.post("/api/browser-sessions", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "live"
    assert body["profile_id"] is None
    assert body["seconds_until_expiry"] is not None
    assert body["seconds_until_expiry"] > 0


def test_session_crud(client: TestClient) -> None:
    created = client.post("/api/browser-sessions", json={}).json()
    session_id = created["id"]

    listed = client.get("/api/browser-sessions").json()
    assert any(row["id"] == session_id for row in listed)

    fetched = client.get(f"/api/browser-sessions/{session_id}").json()
    assert fetched["status"] == "live"

    kept = client.post(f"/api/browser-sessions/{session_id}/keep-alive").json()
    assert kept["status"] == "live"

    closed = client.post(f"/api/browser-sessions/{session_id}/close").json()
    assert closed["status"] == "closed"

    deleted = client.delete(f"/api/browser-sessions/{session_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/browser-sessions/{session_id}").status_code == 404


def test_session_memory_defaults_empty_and_can_clear(client: TestClient) -> None:
    created = client.post("/api/browser-sessions", json={}).json()
    session_id = created["id"]

    empty = client.get(f"/api/browser-sessions/{session_id}/memory")
    assert empty.status_code == 200
    assert empty.json()["entries"] == []

    with Session(engine) as db:
        session_svc.append_memory_entry(
            db,
            session_id,
            objective="download invoice",
            success=True,
            summary="downloaded latest invoice",
            final_url="https://example.com/invoices",
            extracted_items=[{"invoice": "A-1"}],
        )

    listed = client.get(f"/api/browser-sessions/{session_id}/memory")
    assert listed.status_code == 200
    entries = listed.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["objective"] == "download invoice"
    assert entries[0]["success"] is True
    assert entries[0]["summary"] == "downloaded latest invoice"
    assert entries[0]["final_url"] == "https://example.com/invoices"
    assert entries[0]["extracted_summary"] == [{"invoice": "A-1"}]
    assert "dom" not in entries[0]
    assert "screenshot" not in entries[0]

    cleared = client.post(f"/api/browser-sessions/{session_id}/memory/clear")
    assert cleared.status_code == 200
    assert cleared.json()["entries"] == []


def test_session_memory_removed_when_session_deleted(client: TestClient) -> None:
    created = client.post("/api/browser-sessions", json={}).json()
    session_id = created["id"]

    with Session(engine) as db:
        session_svc.append_memory_entry(
            db,
            session_id,
            objective="fill form",
            success=False,
            summary="stopped",
            final_url="https://example.com/form",
            extracted_items=[],
        )

    assert client.delete(f"/api/browser-sessions/{session_id}").status_code == 200
    assert client.get(f"/api/browser-sessions/{session_id}/memory").status_code == 404


def test_max_live_sessions_returns_429(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "max_live_sessions", 2)
    assert client.post("/api/browser-sessions", json={}).status_code == 200
    assert client.post("/api/browser-sessions", json={}).status_code == 200
    resp = client.post("/api/browser-sessions", json={})
    assert resp.status_code == 429
    assert "max live sessions" in resp.json()["detail"].lower()


def test_expire_all_live_on_startup() -> None:
    init_db()
    session_svc.reset_for_tests()
    with Session(engine) as db:
        now = datetime.now(timezone.utc)
        row = BrowserSession(
            status="live",
            started_at=now,
            expires_at=now + timedelta(hours=24),
            last_activity_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        session_id = row.id

    session_svc.expire_all_live_on_startup()

    with Session(engine) as db:
        row = db.get(BrowserSession, session_id)
        assert row is not None
        assert row.status == "expired"


@pytest.mark.asyncio
async def test_idle_eviction_closes_session(
    mock_browser: _FakeBrowser, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_db()
    monkeypatch.setattr(settings, "session_idle_minutes", 0)
    with Session(engine) as db:
        row = await session_svc.create_session(db)
        session_id = row.id

    reaped = await session_svc._reap_once()
    assert reaped == 1

    with Session(engine) as db:
        row = db.get(BrowserSession, session_id)
        assert row is not None
        assert row.status == "closed"
    assert not session_svc.is_active_in_process(session_id)


@pytest.mark.asyncio
async def test_ttl_eviction_marks_expired(
    mock_browser: _FakeBrowser,
) -> None:
    init_db()
    with Session(engine) as db:
        row = await session_svc.create_session(db)
        session_id = row.id
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.add(row)
        db.commit()

    reaped = await session_svc._reap_once()
    assert reaped == 1

    with Session(engine) as db:
        row = db.get(BrowserSession, session_id)
        assert row is not None
        assert row.status == "expired"


@pytest.mark.asyncio
async def test_run_reuses_live_session_context(mock_browser: _FakeBrowser) -> None:
    init_db()
    with Session(engine) as db:
        row = await session_svc.create_session(db)
        session_id = row.id

    run_id = str(uuid.uuid4())
    await browser_tools.begin_run(None, run_id=run_id, browser_session_id=session_id)
    page = browser_tools.get_active_page(run_id)
    assert page is not None

    with Session(engine) as db:
        row = db.get(BrowserSession, session_id)
        assert row is not None
        assert row.last_activity_at is not None

    await browser_tools.end_run(run_id=run_id, browser_session_id=session_id)
    assert session_svc.is_active_in_process(session_id)


def test_run_create_accepts_browser_session_id(
    client: TestClient, seeded_workflow: str
) -> None:
    session = client.post("/api/browser-sessions", json={}).json()
    resp = client.post(
        f"/api/workflows/{seeded_workflow}/runs",
        json={"browser_session_id": session["id"]},
    )
    assert resp.status_code == 200
    assert resp.json()["browser_session_id"] == session["id"]


def test_run_create_rejects_inactive_session(
    client: TestClient, seeded_workflow: str
) -> None:
    resp = client.post(
        f"/api/workflows/{seeded_workflow}/runs",
        json={"browser_session_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 404


def test_run_to_task_spec_injects_browser_session_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.db.models import Run
    from app.services import tasks as task_svc

    monkeypatch.setattr(
        task_svc,
        "_load_browser_session_memory",
        lambda run: [{"objective": "previous", "summary": "logged in"}],
        raising=False,
    )

    spec = task_svc._run_to_task_spec(
        Run(
            workflow_id="wf",
            workflow_version_id="wv",
            mode="autonomous",
            objective="continue task",
            browser_session_id="session-1",
        )
    )

    assert spec.session_memory == [{"objective": "previous", "summary": "logged in"}]
