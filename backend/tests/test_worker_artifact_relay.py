"""Worker artifact upload relay tests."""

from __future__ import annotations

import asyncio
import base64
import sys
import uuid
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.session import init_db
from app.services import artifacts as artifact_svc
from app.services import worker_hub
from app.worker import artifact_relay


@pytest.fixture()
def artifact_tmp(tmp_path: Path):
    root = tmp_path / "artifacts"
    artifact_svc.set_artifact_root(root)
    artifact_svc.reset_seq_counters()
    worker_hub.reset_for_tests()
    artifact_relay.reset_for_tests()
    yield root
    artifact_svc.reset_artifact_root()
    artifact_svc.reset_seq_counters()
    worker_hub.reset_for_tests()
    artifact_relay.reset_for_tests()


@pytest.mark.asyncio
async def test_handle_artifact_upload_stores_on_cloud(artifact_tmp: Path) -> None:
    init_db()
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    worker_id = "worker-1"
    worker_hub._run_to_worker[run_id] = worker_id  # noqa: SLF001

    payload = b"csv,data,here"
    ack = await worker_hub.handle_artifact_upload(
        worker_id,
        {
            "run_id": run_id,
            "upload_id": "up-1",
            "kind": "download",
            "data_base64": base64.b64encode(payload).decode("ascii"),
            "filename": "out.csv",
            "content_type": "text/csv",
        },
    )
    assert ack is not None
    assert ack["artifact_id"]
    row = artifact_svc.get_artifact(ack["artifact_id"], run_id=run_id)
    assert row is not None
    assert artifact_svc.resolve_path(row).read_bytes() == payload


@pytest.mark.asyncio
async def test_relay_event_artifacts_uploads_local_row(artifact_tmp: Path) -> None:
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    local = artifact_svc.store_bytes(
        run_id,
        "download",
        b"worker-output",
        filename="result.bin",
    )
    sent: list[dict] = []

    async def send(frame: dict) -> None:
        sent.append(frame)
        if frame.get("type") == "artifact_upload":
            artifact_relay.handle_ack(
                {
                    "upload_id": frame["upload_id"],
                    "artifact_id": "cloud-artifact-id",
                }
            )

    relayed = await artifact_relay.relay_event_artifacts(
        send,
        run_id,
        {
            "event": "node_completed",
            "output": {"artifact_id": local.id},
        },
    )
    assert sent[0]["type"] == "artifact_upload"
    assert relayed["output"]["artifact_id"] == "cloud-artifact-id"
