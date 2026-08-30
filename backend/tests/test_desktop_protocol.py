"""Tests for desktop runtime message protocol (Phase 4B)."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from app.worker.desktop_api import DesktopApi
from app.worker.desktop_protocol import (
    PROTOCOL_VERSION,
    RequestEnvelope,
    decode_frame,
    decode_request_frame,
    dispatch,
    encode_frame,
    success_response,
)
from app.worker.desktop_runtime import DesktopRuntime


@pytest.fixture
def api() -> DesktopApi:
    runtime = DesktopRuntime(
        approval_status="approved",
        logged_in=True,
        cloud_url="http://127.0.0.1:8001",
        worker_id="wk_test",
        environment={"environment_status": "ready", "checks": []},
    )
    return DesktopApi(runtime)


def test_encode_decode_request_round_trip() -> None:
    req = RequestEnvelope(id="req-1", method="health", params={})
    frame = encode_frame(req)
    decoded = decode_request_frame(frame)
    assert decoded.id == "req-1"
    assert decoded.method == "health"
    assert decoded.v == PROTOCOL_VERSION


def test_encode_decode_response_round_trip() -> None:
    res = success_response("req-1", {"status": "ok"})
    frame = encode_frame(res)
    decoded = decode_frame(frame)
    assert decoded.ok is True
    assert decoded.result == {"status": "ok"}


@pytest.mark.asyncio
async def test_dispatch_health(api: DesktopApi) -> None:
    req = RequestEnvelope(id=str(uuid.uuid4()), method="health", params={})
    res = await dispatch(api, req)
    assert res.ok is True
    assert res.result == {"status": "ok"}


@pytest.mark.asyncio
async def test_dispatch_status(api: DesktopApi) -> None:
    req = RequestEnvelope(id="s1", method="status", params={})
    res = await dispatch(api, req)
    assert res.ok is True
    assert res.result["approval_status"] == "approved"


@pytest.mark.asyncio
async def test_dispatch_unknown_method(api: DesktopApi) -> None:
    req = RequestEnvelope(id="x", method="nope.method", params={})
    res = await dispatch(api, req)
    assert res.ok is False
    assert res.error is not None
    assert res.error.code == "unknown_method"


@pytest.mark.asyncio
async def test_dispatch_computer_use_settings(api: DesktopApi, tmp_path) -> None:
    from app.services.desktop_computer_use.auth import reset_auth_store_for_tests

    store = reset_auth_store_for_tests(tmp_path / "cu-auth.json")
    try:
        req = RequestEnvelope(id="cu1", method="settings.computer_use.get", params={})
        res = await dispatch(api, req)
        assert res.ok is True
        assert "available" in res.result
        assert "always_allowed" in res.result
        assert "reason" in res.result

        put = RequestEnvelope(
            id="cu2",
            method="settings.computer_use.put",
            params={"allow_always": "com.apple.TextEdit"},
        )
        put_res = await dispatch(api, put)
        assert put_res.ok is True
        allowed = {a.lower() for a in put_res.result["always_allowed"]}
        assert "com.apple.textedit" in allowed
        assert "com.apple.textedit" in {a.lower() for a in store.list_always_allowed()}
    finally:
        if (tmp_path / "cu-auth.json").exists():
            (tmp_path / "cu-auth.json").unlink()


def test_frame_length_prefix() -> None:
    req = RequestEnvelope(id="1", method="health", params={})
    frame = encode_frame(req)
    assert len(frame) >= 5
    length = int.from_bytes(frame[:4], "big")
    assert length == len(frame) - 4
