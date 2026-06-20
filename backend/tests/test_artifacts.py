"""Run artifact store, API, and event linkage tests (no real browser)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.models import Run, RunArtifact, Workflow, WorkflowVersion
from app.db.session import engine, init_db
from app.main import app
from app.services import artifact_context
from app.services import artifacts as artifact_svc


@pytest.fixture()
def artifact_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "artifacts"
    artifact_svc.set_artifact_root(root)
    artifact_svc.reset_seq_counters()
    monkeypatch.setattr(
        "app.settings.settings.artifact_retention_days",
        30,
    )
    monkeypatch.setattr(
        "app.settings.settings.max_artifact_bytes",
        1024 * 1024,
    )
    yield root
    artifact_svc.reset_artifact_root()
    artifact_svc.reset_seq_counters()
    artifact_context.clear_run_context()


@pytest.fixture()
def seeded_run(artifact_tmp: Path) -> str:
    init_db()
    with Session(engine) as session:
        wf = Workflow(name="artifact-test-wf")
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


def test_store_screenshot_and_dedupe(artifact_tmp: Path, seeded_run: str) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    a1 = artifact_svc.store_screenshot(seeded_run, png, node_id="n1", step_index=0)
    a2 = artifact_svc.store_screenshot(seeded_run, png, node_id="n1", step_index=1)

    assert a1.id == a2.id
    assert a1.content_hash == a2.content_hash
    file_path = artifact_svc.resolve_path(a1)
    assert file_path.is_file()
    assert file_path.read_bytes() == png

    rows = artifact_svc.list_artifacts(seeded_run, kind="screenshot")
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_enrich_vision_step_links_artifact_id(
    artifact_tmp: Path,
    seeded_run: str,
    tmp_path: Path,
) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"step-bytes"
    ref = tmp_path / "ephemeral.png"
    ref.write_bytes(png)

    payload = {
        "event": "vision_step",
        "node_id": "vn1",
        "step_index": 2,
        "screenshot_ref": str(ref),
        "action": "click_element",
    }
    enriched = await artifact_svc.enrich_event_payload(seeded_run, payload)

    assert "artifact_id" in enriched
    row = artifact_svc.get_artifact(enriched["artifact_id"], run_id=seeded_run)
    assert row is not None
    assert row.kind == "screenshot"
    assert row.node_id == "vn1"
    assert row.step_index == 2


def test_retention_reaper_tombstones_and_deletes_file(
    artifact_tmp: Path,
    seeded_run: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.settings.settings.artifact_retention_days", 1)
    png = b"\x89PNG\r\n\x1a\n" + b"old"
    row = artifact_svc.store_screenshot(seeded_run, png)
    file_path = artifact_svc.resolve_path(row)
    assert file_path.is_file()

    with Session(engine) as session:
        db_row = session.get(RunArtifact, row.id)
        assert db_row is not None
        db_row.created_at = datetime.now(timezone.utc) - timedelta(days=2)
        session.add(db_row)
        session.commit()

    removed = artifact_svc.reap_expired_artifacts()
    assert removed == 1
    assert not file_path.is_file()

    with Session(engine) as session:
        db_row = session.get(RunArtifact, row.id)
        assert db_row is not None
        assert db_row.deleted_at is not None


def test_artifact_api_list_and_fetch(artifact_tmp: Path, seeded_run: str) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"api-test"
    row = artifact_svc.store_screenshot(seeded_run, png, node_id="n2")

    client = TestClient(app)
    list_resp = client.get(f"/api/runs/{seeded_run}/artifacts?kind=screenshot")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["id"] == row.id
    assert items[0]["kind"] == "screenshot"

    fetch_resp = client.get(f"/api/runs/{seeded_run}/artifacts/{row.id}")
    assert fetch_resp.status_code == 200
    assert fetch_resp.content == png

    thumb_resp = client.get(
        f"/api/runs/{seeded_run}/artifacts/{row.id}/thumbnail"
    )
    assert thumb_resp.status_code == 200
    assert thumb_resp.content == png


def test_store_trace_and_download_kinds(artifact_tmp: Path, seeded_run: str) -> None:
    trace = artifact_svc.store_trace_json(
        seeded_run,
        {"model": "gpt-4o", "response": "ok"},
        node_id="n3",
    )
    assert trace.kind == "llm_trace"
    assert trace.content_type == "application/json"

    dl = artifact_svc.store_bytes(
        seeded_run,
        "download",
        b"file-content",
        filename="report.csv",
        content_type="text/csv",
    )
    assert dl.kind == "download"
    assert dl.filename == "report.csv"

    counts = artifact_svc.count_by_kind(seeded_run)
    assert counts.get("screenshot", 0) == 0
    assert counts["llm_trace"] == 1
    assert counts["download"] == 1


def test_oversize_download_note(
    artifact_tmp: Path,
    seeded_run: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.settings.settings.max_artifact_bytes", 50)
    big = b"x" * 200
    row = artifact_svc.store_bytes(seeded_run, "download", big)
    assert row.note == "过大未内联"
    assert row.bytes == 0
    assert not artifact_svc.resolve_path(row).is_file()


def test_run_out_includes_artifact_counts(artifact_tmp: Path, seeded_run: str) -> None:
    artifact_svc.store_screenshot(seeded_run, b"\x89PNG\r\n\x1a\n\x00")
    artifact_svc.store_trace_json(seeded_run, {"x": 1})

    client = TestClient(app)
    resp = client.get(f"/api/runs/{seeded_run}")
    assert resp.status_code == 200
    run = resp.json()["run"]
    assert run["artifact_counts"]["screenshot"] == 1
    assert run["artifact_counts"]["llm_trace"] == 1
