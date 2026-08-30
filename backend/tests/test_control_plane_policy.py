"""Control-plane policy rejects edge-local writes on cloud deployments."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.settings import settings


@pytest.fixture()
def control_plane(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "execution_backend", "control_plane_only")


def test_create_workflow_blocked_on_control_plane(
    client: TestClient, control_plane: None
) -> None:
    res = client.post(
        "/api/workflows",
        json={"name": f"blocked-{uuid.uuid4().hex[:8]}"},
    )
    assert res.status_code == 403
    assert "desktop client" in res.json()["detail"].lower()


def test_create_credential_blocked_on_control_plane(
    client: TestClient, control_plane: None
) -> None:
    res = client.post(
        "/api/credentials",
        json={
            "name": f"cred-{uuid.uuid4().hex[:8]}",
            "fields": {"username": "u", "password": "p"},
        },
    )
    assert res.status_code == 403
    assert "desktop client" in res.json()["detail"].lower()


def test_create_recording_blocked_on_control_plane(
    client: TestClient, control_plane: None
) -> None:
    res = client.post("/api/recordings", json={})
    assert res.status_code == 403
    assert "desktop client" in res.json()["detail"].lower()


def test_create_browser_session_blocked_on_control_plane(
    client: TestClient, control_plane: None
) -> None:
    res = client.post("/api/browser-sessions", json={})
    assert res.status_code == 403
    assert "desktop client" in res.json()["detail"].lower()


def test_create_browser_profile_blocked_on_control_plane(
    client: TestClient, control_plane: None
) -> None:
    res = client.post(
        "/api/browser-profiles",
        json={"name": f"profile-{uuid.uuid4().hex[:8]}"},
    )
    assert res.status_code == 403
    assert "desktop client" in res.json()["detail"].lower()


def test_create_workflow_allowed_when_full_backend(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "execution_backend", "full")
    name = f"allowed-{uuid.uuid4().hex[:8]}"
    res = client.post("/api/workflows", json={"name": name})
    assert res.status_code == 200, res.text
    wf_id = res.json()["id"]
    client.delete(f"/api/workflows/{wf_id}")
