"""Session recording artifact tests (mocked frames / ffmpeg, no real browser)."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.models import Run, Workflow, WorkflowVersion
from app.db.session import engine, init_db
from app.main import app
from app.services import artifacts as artifact_svc
from app.services import session_recording as rec_svc


@pytest.fixture()
def artifact_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "artifacts"
    artifact_svc.set_artifact_root(root)
    artifact_svc.reset_seq_counters()
    rec_svc.reset_for_tests()
    monkeypatch.setattr("app.settings.settings.video_recording_enabled", False)
    yield root
    artifact_svc.reset_artifact_root()
    artifact_svc.reset_seq_counters()
    rec_svc.reset_for_tests()


@pytest.fixture()
def seeded_run(artifact_tmp: Path) -> str:
    init_db()
    with Session(engine) as session:
        wf = Workflow(name="recording-test-wf")
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


def _fake_jpeg_b64(label: bytes = b"A") -> str:
    return base64.b64encode(b"\xff\xd8\xff" + label).decode("ascii")


async def _inject_test_frames(run_id: str, count: int = 2) -> None:
    recorder = rec_svc.SessionRecorder(run_id=run_id)
    rec_svc._recorders[run_id] = recorder
    for i in range(count):
        await recorder.inject_frame(_fake_jpeg_b64(bytes([i])), width=640, height=480)


def test_is_enabled_respects_global_and_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.settings.settings.video_recording_enabled", False)
    assert rec_svc.is_enabled(None) is False
    assert rec_svc.is_enabled(True) is True
    assert rec_svc.is_enabled(False) is False

    monkeypatch.setattr("app.settings.settings.video_recording_enabled", True)
    assert rec_svc.is_enabled(None) is True
    assert rec_svc.is_enabled(False) is False


@pytest.mark.asyncio
async def test_recording_disabled_produces_no_artifact(
    artifact_tmp: Path,
    seeded_run: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.settings.settings.video_recording_enabled", False)
    assert rec_svc.is_enabled(None) is False
    await rec_svc.finalize_recording(seeded_run)
    assert artifact_svc.list_artifacts(seeded_run, kind="recording") == []


@pytest.mark.asyncio
async def test_recording_produces_mp4_with_ffmpeg(
    artifact_tmp: Path,
    seeded_run: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_mp4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32
    await _inject_test_frames(seeded_run)
    monkeypatch.setattr(rec_svc, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(rec_svc, "mux_frames_to_mp4", lambda frames, fps=8: fake_mp4)

    await rec_svc.finalize_recording(seeded_run)

    rows = artifact_svc.list_artifacts(seeded_run, kind="recording")
    assert len(rows) == 1
    assert rows[0].content_type == "video/mp4"
    assert artifact_svc.resolve_path(rows[0]).read_bytes() == fake_mp4


@pytest.mark.asyncio
async def test_recording_produces_frame_manifest_without_ffmpeg(
    artifact_tmp: Path,
    seeded_run: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _inject_test_frames(seeded_run, count=3)
    monkeypatch.setattr(rec_svc, "ffmpeg_available", lambda: False)

    await rec_svc.finalize_recording(seeded_run)

    rows = artifact_svc.list_artifacts(seeded_run, kind="recording")
    assert len(rows) == 1
    assert rows[0].content_type == "application/json"
    assert rows[0].note == "ffmpeg unavailable; frame manifest playback"
    payload = json.loads(artifact_svc.resolve_path(rows[0]).read_text())
    assert payload["format"] == "frame_manifest"
    assert len(payload["frames"]) == 3


@pytest.mark.asyncio
async def test_recording_api_list_and_download(
    artifact_tmp: Path,
    seeded_run: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_mp4 = b"\x00\x00\x00\x18ftypmp42" + b"video-bytes"
    await _inject_test_frames(seeded_run)
    monkeypatch.setattr(rec_svc, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(rec_svc, "mux_frames_to_mp4", lambda frames, fps=8: fake_mp4)
    await rec_svc.finalize_recording(seeded_run)

    client = TestClient(app)
    list_resp = client.get(f"/api/runs/{seeded_run}/artifacts?kind=recording")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["kind"] == "recording"

    artifact_id = items[0]["id"]
    fetch_resp = client.get(f"/api/runs/{seeded_run}/artifacts/{artifact_id}")
    assert fetch_resp.status_code == 200
    assert fetch_resp.content == fake_mp4


def test_mux_frames_to_mp4_returns_none_without_frames() -> None:
    assert rec_svc.mux_frames_to_mp4([], fps=8) is None


def test_build_frame_manifest_shape() -> None:
    frame = rec_svc._Frame(
        ts="2026-01-01T00:00:00+00:00",
        seq=1,
        width=100,
        height=80,
        data=_fake_jpeg_b64(),
    )
    raw = rec_svc.build_frame_manifest([frame], fps=8)
    payload = json.loads(raw.decode())
    assert payload["fps"] == 8
    assert payload["frames"][0]["seq"] == 1
