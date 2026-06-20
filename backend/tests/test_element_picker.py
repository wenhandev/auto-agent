"""Element picker API tests."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.main import app
from app.services import browser_pool
from app.services import browser_profiles as profile_svc
from app.services import browser_sessions as session_svc


class _FakeLocator:
    def __init__(self, count: int = 1) -> None:
        self._count = count

    async def count(self) -> int:
        return self._count

    @property
    def first(self) -> "_FakeLocator":
        return self

    async def evaluate(self, _js: str) -> dict:
        return {
            "tag": "button",
            "text": "Continue",
            "role": "button",
            "visible": True,
        }


class _FakePage:
    is_closed = False
    url = "about:blank"

    def __init__(self, context: object) -> None:
        self.context = context
        self.viewport_size = {"width": 800, "height": 600}

    async def goto(self, url: str, **kwargs) -> None:
        self.url = url

    async def title(self) -> str:
        return "Test"

    async def screenshot(self, **kwargs) -> bytes:
        return b"\xff\xd8\xff\xe0fakejpeg"

    def locator(self, selector: str) -> _FakeLocator:
        return _FakeLocator(count=1)

    def get_by_text(self, text: str, exact: bool = False) -> _FakeLocator:
        return _FakeLocator(count=1)

    async def evaluate(self, js: str, arg=None) -> dict:
        if arg and isinstance(arg, list) and len(arg) == 2:
            x, y = arg
            if x < 0 or y < 0:
                return {
                    "error": "coordinates outside viewport",
                    "viewport": {"width": 800, "height": 600},
                }
            return {
                "element": {
                    "tag": "button",
                    "id": "login-submit-btn",
                    "dataTestId": "login-submit",
                    "name": None,
                    "ariaLabel": "Continue",
                    "text": "Continue",
                    "role": "button",
                    "cssPath": "button#login-submit-btn",
                },
                "viewport": {"width": 800, "height": 600},
            }
        return {}


class _FakeContext:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    async def close(self) -> None:
        pass

    async def new_page(self) -> _FakePage:
        return _FakePage(self)


class _FakeBrowser:
    def is_connected(self) -> bool:
        return True

    async def new_context(self, **kwargs) -> _FakeContext:
        return _FakeContext(**kwargs)

    async def close(self) -> None:
        pass


@pytest.fixture()
def profiles_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "profiles"
    profile_svc.set_profiles_root(root)
    yield root
    profile_svc.reset_profiles_root()


@pytest.fixture()
def mock_browser(monkeypatch: pytest.MonkeyPatch):
    fake = _FakeBrowser()
    monkeypatch.setattr(browser_pool, "_browser", fake)
    monkeypatch.setattr(browser_pool, "_playwright", MagicMock())
    browser_pool.reset_for_tests()
    session_svc.reset_for_tests()
    yield fake
    browser_pool.reset_for_tests()
    session_svc.reset_for_tests()


@pytest.fixture()
def client(profiles_tmp: Path, mock_browser: _FakeBrowser) -> TestClient:
    return TestClient(app)


def _create_session(client: TestClient) -> str:
    return client.post("/api/browser-sessions", json={}).json()["id"]


def test_picker_enable_disable(client: TestClient) -> None:
    session_id = _create_session(client)
    enabled = client.post(
        f"/api/browser-sessions/{session_id}/picker/enable",
        json={"mode": "coordinate"},
    )
    assert enabled.status_code == 200
    token = enabled.json()["picker_token"]

    disabled = client.post(
        f"/api/browser-sessions/{session_id}/picker/disable",
        json={"picker_token": token},
    )
    assert disabled.status_code == 200


def test_picker_navigate_screenshot_pick_test(client: TestClient) -> None:
    session_id = _create_session(client)
    token = client.post(
        f"/api/browser-sessions/{session_id}/picker/enable", json={}
    ).json()["picker_token"]

    nav = client.post(
        f"/api/browser-sessions/{session_id}/navigate",
        json={
            "picker_token": token,
            "url": "http://localhost:8765/static/portal/index.html",
        },
    )
    assert nav.status_code == 200

    shot = client.get(
        f"/api/browser-sessions/{session_id}/screenshot",
        params={"picker_token": token},
    )
    assert shot.status_code == 200
    assert shot.headers["content-type"] == "image/jpeg"
    assert shot.headers["x-viewport-width"] == "800"

    picked = client.post(
        f"/api/browser-sessions/{session_id}/pick-element",
        json={"picker_token": token, "x": 100, "y": 200},
    )
    assert picked.status_code == 200
    body = picked.json()
    assert body.get("error") is None
    assert len(body["candidates"]) >= 1
    assert body["candidates"][0]["match_count"] >= 1

    selector = body["candidates"][0]["selector"]
    tested = client.post(
        f"/api/browser-sessions/{session_id}/test-selector",
        json={"picker_token": token, "selector": selector},
    )
    assert tested.status_code == 200
    assert tested.json()["match_count"] == 1

    client.post(
        f"/api/browser-sessions/{session_id}/picker/disable",
        json={"picker_token": token},
    )


def test_picker_blocks_second_enable(client: TestClient) -> None:
    session_id = _create_session(client)
    client.post(f"/api/browser-sessions/{session_id}/picker/enable", json={})
    resp = client.post(f"/api/browser-sessions/{session_id}/picker/enable", json={})
    assert resp.status_code == 409
