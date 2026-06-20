"""Browser download auto-capture and HAR artifact tests (mocked, no real browser)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.models import Run, Workflow, WorkflowVersion
from app.db.session import engine, init_db
from app.services import browser_capture
from app.services import artifacts as artifact_svc
from sqlmodel import Session


@pytest.fixture()
def artifact_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "artifacts"
    artifact_svc.set_artifact_root(root)
    artifact_svc.reset_seq_counters()
    browser_capture.reset_for_tests()
    monkeypatch.setattr("app.settings.settings.har_enabled", False)
    yield root
    artifact_svc.reset_artifact_root()
    artifact_svc.reset_seq_counters()
    browser_capture.reset_for_tests()


@pytest.fixture()
def seeded_run(artifact_tmp: Path) -> str:
    init_db()
    with Session(engine) as session:
        wf = Workflow(name="capture-test-wf")
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
        run = Run(
            workflow_id=wf.id,
            workflow_version_id=version.id,
            status="completed",
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        return run.id


@pytest.mark.asyncio
async def test_auto_capture_browser_download(
    artifact_tmp: Path,
    seeded_run: str,
    tmp_path: Path,
) -> None:
    dl_path = tmp_path / "export.csv"
    dl_path.write_bytes(b"col1,col2\n1,2")

    download = AsyncMock()
    download.path = AsyncMock(return_value=str(dl_path))
    download.suggested_filename = "export.csv"

    handlers: list = []

    page = MagicMock()

    def capture_handler(event: str, handler):
        assert event == "download"
        handlers.append(handler)

    page.on = capture_handler

    browser_capture.attach_download_listener(seeded_run, page)
    assert len(handlers) == 1

    handlers[0](download)
    import asyncio

    await asyncio.sleep(0.05)

    rows = artifact_svc.list_artifacts(seeded_run, kind="download")
    assert len(rows) == 1
    assert rows[0].filename == "export.csv"
    assert artifact_svc.resolve_path(rows[0]).read_bytes() == b"col1,col2\n1,2"


def test_prepare_har_context_option_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser_capture.reset_for_tests()
    monkeypatch.setattr("app.settings.settings.har_enabled", False)
    assert browser_capture.prepare_har_context_option("run-1") == {}


def test_prepare_har_context_option_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser_capture.reset_for_tests()
    monkeypatch.setattr("app.settings.settings.har_enabled", True)
    opts = browser_capture.prepare_har_context_option("run-har-1")
    assert "record_har_path" in opts
    path = Path(opts["record_har_path"])
    assert path.suffix == ".har"
    assert browser_capture.pop_har_path("run-har-1") == path


def test_persist_har_artifact(
    artifact_tmp: Path,
    seeded_run: str,
    tmp_path: Path,
) -> None:
    har_bytes = json.dumps({"log": {"version": "1.2", "entries": []}}).encode()
    har_path = tmp_path / "session.har"
    har_path.write_bytes(har_bytes)

    browser_capture.persist_har_artifact(seeded_run, har_path)

    assert not har_path.exists()
    rows = artifact_svc.list_artifacts(seeded_run, kind="har")
    assert len(rows) == 1
    assert rows[0].content_type == "application/json"
    assert artifact_svc.resolve_path(rows[0]).read_bytes() == har_bytes


def test_har_kind_in_api_schema(artifact_tmp: Path, seeded_run: str) -> None:
    har_bytes = b'{"log":{"version":"1.2","entries":[]}}'
    row = artifact_svc.store_bytes(
        seeded_run,
        "har",
        har_bytes,
        filename="network.har",
    )

    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    list_resp = client.get(f"/api/runs/{seeded_run}/artifacts?kind=har")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["id"] == row.id
    assert items[0]["kind"] == "har"

    fetch_resp = client.get(f"/api/runs/{seeded_run}/artifacts/{row.id}")
    assert fetch_resp.status_code == 200
    assert fetch_resp.content == har_bytes


def test_download_listener_idempotent(seeded_run: str) -> None:
    browser_capture.reset_for_tests()
    calls = {"n": 0}
    page = MagicMock()

    def on(event, handler):
        calls["n"] += 1

    page.on = on
    browser_capture.attach_download_listener(seeded_run, page)
    browser_capture.attach_download_listener(seeded_run, page)
    assert calls["n"] == 1
