"""Browser profile storage, API, and run wiring tests (mock Playwright)."""

from __future__ import annotations

import json
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

from app.db.crypto import decrypt, encrypt, load_or_create_key
from app.db.models import BrowserProfile, Run, Workflow, WorkflowVersion
from app.db.session import engine, init_db
from app.main import app
from app.services import browser_profiles as profile_svc
from app.services import browser_pool
from app.tools import browser as browser_tools


def _unique_name(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.fixture()
def profiles_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "profiles"
    profile_svc.set_profiles_root(root)
    load_or_create_key()
    yield root
    profile_svc.reset_profiles_root()


@pytest.fixture()
def client(profiles_tmp: Path) -> TestClient:
    return TestClient(app)


@pytest.fixture()
def seeded_workflow(profiles_tmp: Path) -> str:
    init_db()
    with Session(engine) as session:
        wf = Workflow(name="profile-test-wf")
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


def test_create_profile_writes_encrypted_empty_state(profiles_tmp: Path, client: TestClient) -> None:
    resp = client.post(
        "/api/browser-profiles",
        json={"name": _unique_name("test-profile"), "user_agent": "TestAgent/1.0"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"].startswith("test-profile-")
    assert body["user_agent"] == "TestAgent/1.0"
    assert body["has_storage_state"] is False

    enc_path = profiles_tmp / body["id"] / "storage_state.enc"
    assert enc_path.is_file()
    plain = decrypt(enc_path.read_bytes())
    state = json.loads(plain.decode("utf-8"))
    assert state == {"cookies": [], "origins": []}


def test_profile_crud(client: TestClient) -> None:
    name = _unique_name("crud-profile")
    created = client.post("/api/browser-profiles", json={"name": name}).json()
    profile_id = created["id"]

    listed = client.get("/api/browser-profiles").json()
    assert any(row["id"] == profile_id for row in listed)

    fetched = client.get(f"/api/browser-profiles/{profile_id}").json()
    assert fetched["name"] == name

    renamed = _unique_name("renamed-profile")
    updated = client.patch(
        f"/api/browser-profiles/{profile_id}",
        json={"name": renamed, "viewport": {"width": 800, "height": 600}},
    ).json()
    assert updated["name"] == renamed
    assert updated["viewport"] == {"width": 800, "height": 600}

    deleted = client.delete(f"/api/browser-profiles/{profile_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/browser-profiles/{profile_id}").status_code == 404


def test_profile_name_unique(client: TestClient) -> None:
    name = _unique_name("dup-name")
    client.post("/api/browser-profiles", json={"name": name})
    resp = client.post("/api/browser-profiles", json={"name": name})
    assert resp.status_code == 409


def test_storage_state_round_trip(profiles_tmp: Path) -> None:
    init_db()
    with Session(engine) as session:
        profile = profile_svc.create_profile_row(name=_unique_name("round-trip"), session=session)

    sample = {
        "cookies": [{"name": "sid", "value": "abc", "domain": "example.com", "path": "/"}],
        "origins": [
            {
                "origin": "https://example.com",
                "localStorage": [{"name": "token", "value": "xyz"}],
            }
        ],
    }
    profile_svc.write_storage_state(profile.id, sample)
    loaded = profile_svc.read_storage_state(profile.id)
    assert loaded["cookies"][0]["name"] == "sid"
    assert loaded["origins"][0]["localStorage"][0]["value"] == "xyz"
    assert profile_svc.has_storage_state(profile.id) is True


@pytest.mark.asyncio
async def test_begin_run_loads_profile_context(
    profiles_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_db()
    with Session(engine) as session:
        profile = profile_svc.create_profile_row(
            name=_unique_name("seed-profile"),
            user_agent="SeedAgent/2.0",
            viewport={"width": 1024, "height": 768},
            session=session,
        )
    profile_svc.write_storage_state(
        profile.id,
        {
            "cookies": [{"name": "auth", "value": "yes", "domain": "app.test", "path": "/"}],
            "origins": [],
        },
    )

    captured: dict = {}

    class _FakePage:
        is_closed = False

        def __init__(self, context: object) -> None:
            self.context = context

    class _FakeContext:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        async def close(self) -> None:
            pass

        async def new_page(self) -> _FakePage:
            return _FakePage(self)

    class _FakeBrowser:
        def is_connected(self) -> bool:
            return True

        async def new_context(self, **kwargs) -> _FakeContext:
            captured.update(kwargs)
            return _FakeContext(**kwargs)

        async def close(self) -> None:
            pass

    fake_browser = _FakeBrowser()
    monkeypatch.setattr(browser_pool, "_browser", fake_browser)
    monkeypatch.setattr(browser_pool, "_playwright", MagicMock())
    browser_pool.reset_for_tests()

    await browser_tools.begin_run(profile.id)

    assert captured["user_agent"] == "SeedAgent/2.0"
    assert captured["viewport"] == {"width": 1024, "height": 768}
    assert captured["storage_state"]["cookies"][0]["name"] == "auth"
    await browser_tools.end_run()


@pytest.mark.asyncio
async def test_end_run_persists_storage_state(
    profiles_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_db()
    with Session(engine) as session:
        profile = profile_svc.create_profile_row(name=_unique_name("persist-profile"), session=session)

    saved_state = {
        "cookies": [{"name": "session", "value": "saved", "domain": "x.test", "path": "/"}],
        "origins": [],
    }

    fake_context = AsyncMock()
    fake_context.storage_state = AsyncMock(return_value=saved_state)

    monkeypatch.setattr(browser_pool, "_active", {})
    monkeypatch.setattr(browser_pool, "_parked", {})
    rb = browser_pool._RunBrowser(
        run_id="__legacy__",
        context=fake_context,
        page=MagicMock(is_closed=lambda: False),
        profile_id=profile.id,
    )
    browser_pool._active["__legacy__"] = rb
    monkeypatch.setattr(browser_tools, "_legacy_run_id", "__legacy__")
    monkeypatch.setattr(browser_tools, "_active_profile_id", profile.id)

    await browser_tools.end_run()

    loaded = profile_svc.read_storage_state(profile.id)
    assert loaded["cookies"][0]["value"] == "saved"

    with Session(engine) as session:
        row = session.get(BrowserProfile, profile.id)
        assert row is not None
        assert row.last_used_at is not None


def test_run_create_accepts_browser_profile_id(
    client: TestClient, seeded_workflow: str
) -> None:
    profile = client.post(
        "/api/browser-profiles", json={"name": _unique_name("run-profile")}
    ).json()
    resp = client.post(
        f"/api/workflows/{seeded_workflow}/runs",
        json={"browser_profile_id": profile["id"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["browser_profile_id"] == profile["id"]


def test_run_create_rejects_missing_profile(
    client: TestClient, seeded_workflow: str
) -> None:
    resp = client.post(
        f"/api/workflows/{seeded_workflow}/runs",
        json={"browser_profile_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_capture_from_run_updates_profile(
    profiles_tmp: Path, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_db()
    with Session(engine) as session:
        wf = Workflow(name="capture-wf")
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
        run = Run(workflow_id=wf.id, workflow_version_id=version.id, status="running")
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id

    profile = client.post(
        "/api/browser-profiles", json={"name": _unique_name("capture-profile")}
    ).json()
    profile_id = profile["id"]

    captured = {
        "cookies": [{"name": "captured", "value": "1", "domain": "site.test", "path": "/"}],
        "origins": [],
    }
    fake_context = AsyncMock()
    fake_context.storage_state = AsyncMock(return_value=captured)
    monkeypatch.setattr(browser_tools, "get_active_context", lambda: fake_context)

    resp = client.post(f"/api/browser-profiles/{profile_id}/capture-from-run/{run_id}")
    assert resp.status_code == 200
    assert resp.json()["has_storage_state"] is True

    loaded = profile_svc.read_storage_state(profile_id)
    assert loaded["cookies"][0]["name"] == "captured"
