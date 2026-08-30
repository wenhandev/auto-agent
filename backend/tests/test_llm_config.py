"""LLM config API tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.session import init_db
from app.main import app


@pytest.fixture(autouse=True)
def _fresh_db():
    init_db()
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_effective_returns_none_when_unconfigured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _no_config(session=None):
        raise RuntimeError("no config")

    monkeypatch.setattr("app.services.llm_runtime.effective_settings", _no_config)
    res = client.get("/api/llm-config/effective")
    assert res.status_code == 200
    body = res.json()
    assert body["source"] == "none"
    assert body["provider"] is None
    assert body["model"] is None
    assert body["api_key_masked"] == ""


def test_upsert_rejects_email_as_model(client: TestClient) -> None:
    res = client.post(
        "/api/llm-config",
        json={
            "provider": "openai",
            "model": "admin@wenhandev.com",
            "api_key": "sk-test-key",
        },
    )
    assert res.status_code == 422
