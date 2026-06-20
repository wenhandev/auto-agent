"""Smoke tests for the Acme Supply Hub demo portal."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


PORTAL_DIR = Path(__file__).resolve().parents[1] / "static" / "portal"
REQUIRED_FILES = ("index.html", "styles.css", "app.js")


@pytest.mark.parametrize("filename", REQUIRED_FILES)
def test_portal_static_files_exist(filename: str) -> None:
    assert (PORTAL_DIR / filename).is_file()


def test_demo_redirect(client: TestClient) -> None:
    resp = client.get("/demo", follow_redirects=False)
    assert resp.status_code in (301, 302, 307, 308)
    assert resp.headers["location"] == "/static/portal/index.html"


def test_portal_index_served(client: TestClient) -> None:
    resp = client.get("/static/portal/index.html")
    assert resp.status_code == 200
    assert "Acme Supply Hub" in resp.text
    assert 'data-testid="login-form"' in resp.text
    assert 'data-testid="nav-orders"' in resp.text


def test_portal_assets_served(client: TestClient) -> None:
    for asset in ("styles.css", "app.js"):
        resp = client.get(f"/static/portal/{asset}")
        assert resp.status_code == 200
        assert len(resp.content) > 100


def test_portal_contains_demo_credentials_in_js(client: TestClient) -> None:
    resp = client.get("/static/portal/app.js")
    assert resp.status_code == 200
    body = resp.text
    assert "demo@acme.com" in body
    assert "demo1234" in body
    assert "123456" in body


def test_portal_has_extract_targets(client: TestClient) -> None:
    html_resp = client.get("/static/portal/index.html")
    html = html_resp.text
    for testid in (
        "invoice-json",
        "ticket-json",
        "orders-filter-form",
        "support-wizard",
    ):
        assert f'data-testid="{testid}"' in html

    js_resp = client.get("/static/portal/app.js")
    assert 'data-testid="order-json"' in js_resp.text
