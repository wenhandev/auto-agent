from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.nodes import read_file, write_file
from app.tools.sandbox import SandboxViolation, WORKSPACE_DIR, workflow_dir


@pytest.fixture
def wf_id():
    wid = f"test_{uuid.uuid4().hex[:8]}"
    yield wid
    import shutil

    shutil.rmtree(workflow_dir(wid), ignore_errors=True)


def test_write_then_read_round_trip(wf_id):
    asyncio.run(
        write_file.run(
            {"path": "t.txt", "contents": "hello-A"},
            input_items=[],
            context={},
            workflow_id=wf_id,
        )
    )
    items = asyncio.run(
        read_file.run(
            {"path": "t.txt"},
            input_items=[],
            context={},
            workflow_id=wf_id,
        )
    )
    assert items[0].json["contents"] == "hello-A"
    assert (WORKSPACE_DIR / wf_id / "t.txt").read_text() == "hello-A"


def test_per_workflow_isolation(wf_id):
    wf_b = f"test_{uuid.uuid4().hex[:8]}"
    try:
        asyncio.run(
            write_file.run(
                {"path": "t.txt", "contents": "hello-A"},
                input_items=[],
                context={},
                workflow_id=wf_id,
            )
        )
        with pytest.raises(FileNotFoundError):
            asyncio.run(
                read_file.run(
                    {"path": "t.txt"},
                    input_items=[],
                    context={},
                    workflow_id=wf_b,
                )
            )
    finally:
        import shutil

        shutil.rmtree(workflow_dir(wf_b), ignore_errors=True)


def test_traversal_rejected(wf_id):
    with pytest.raises(SandboxViolation):
        asyncio.run(
            write_file.run(
                {"path": "../../escape.txt", "contents": "x"},
                input_items=[],
                context={},
                workflow_id=wf_id,
            )
        )


def test_absolute_path_rejected(wf_id):
    with pytest.raises(SandboxViolation, match="absolute"):
        asyncio.run(
            read_file.run(
                {"path": "/etc/passwd"},
                input_items=[],
                context={},
                workflow_id=wf_id,
            )
        )


def test_ephemeral_run_rejected():
    with pytest.raises(SandboxViolation, match="persisted workflow"):
        asyncio.run(
            read_file.run({"path": "t.txt"}, input_items=[], context={}, workflow_id=None)
        )


def test_max_bytes_enforced(wf_id):
    path = workflow_dir(wf_id) / "big.txt"
    path.write_text("x" * 200)
    with pytest.raises(ValueError, match="max_bytes"):
        asyncio.run(
            read_file.run(
                {"path": "big.txt", "max_bytes": 50},
                input_items=[],
                context={},
                workflow_id=wf_id,
            )
        )
