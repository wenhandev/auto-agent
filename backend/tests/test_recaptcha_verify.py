"""Tests for reCAPTCHA test verification endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def verify_ok_response() -> dict:
    return {
        "success": True,
        "challenge_ts": "2024-01-01T00:00:00Z",
        "hostname": "127.0.0.1",
    }


@pytest.fixture()
def verify_fail_response() -> dict:
    return {"success": False, "error-codes": ["invalid-input-response"]}


def test_recaptcha_config(client: TestClient) -> None:
    resp = client.get("/api/test/recaptcha-config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["site_key"]


def test_recaptcha_verify_success(client: TestClient, verify_ok_response: dict) -> None:
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = lambda: None
    mock_resp.json = lambda: verify_ok_response

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.routers.recaptcha_test.httpx.AsyncClient", return_value=mock_client):
        resp = client.post(
            "/api/test/recaptcha-verify",
            data={
                "g-recaptcha-response": "test-token-abc",
                "password": "SecretPass123",
                "name": "Jane Agent",
                "email": "jane@example.com",
                "phone": "+1 555 0199",
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["fields"]["name"] == "Jane Agent"
    assert body["fields"]["email"] == "jane@example.com"
    assert body["recaptcha"]["hostname"] == "127.0.0.1"


def test_recaptcha_verify_google_rejects(client: TestClient, verify_fail_response: dict) -> None:
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = lambda: None
    mock_resp.json = lambda: verify_fail_response

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.routers.recaptcha_test.httpx.AsyncClient", return_value=mock_client):
        resp = client.post(
            "/api/test/recaptcha-verify",
            data={"g-recaptcha-response": "bad-token"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert "invalid-input-response" in body.get("error_codes", [])


def test_recaptcha_verify_missing_token(client: TestClient) -> None:
    resp = client.post("/api/test/recaptcha-verify", data={})
    assert resp.status_code == 422
