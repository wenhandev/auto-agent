from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx
import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.nodes import http_request as http_request_node
from app.nodes._http_client import SSRFError, request, validate_url


def test_validate_url_blocks_localhost():
    with pytest.raises(SSRFError, match="blocked"):
        validate_url("http://127.0.0.1/api")


def test_validate_url_blocks_file_scheme():
    with pytest.raises(SSRFError, match="scheme"):
        validate_url("file:///etc/passwd")


@pytest.mark.asyncio
async def test_get_json_happy_path():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={"id": 42},
            headers={"content-type": "application/json"},
        )

    transport = httpx.MockTransport(handler)
    out = await request(
        method="GET",
        url="https://api.example.com/order/42",
        transport=transport,
    )
    assert out["status"] == 200
    assert out["json"] == {"id": 42}
    assert "42" in out["text"]
    assert isinstance(out["elapsed_ms"], int)


@pytest.mark.asyncio
async def test_4xx_completes_not_raises():
    transport = httpx.MockTransport(
        lambda r: httpx.Response(404, text="not found")
    )
    out = await request(method="GET", url="https://api.example.com/x", transport=transport)
    assert out["status"] == 404


@pytest.mark.asyncio
async def test_network_error_raises():
    transport = httpx.MockTransport(
        lambda r: (_ for _ in ()).throw(httpx.ConnectError("connection refused"))
    )
    with pytest.raises(httpx.ConnectError):
        await request(method="GET", url="https://api.example.com/x", transport=transport)


@pytest.mark.asyncio
async def test_node_run_returns_item():
    transport = httpx.MockTransport(
        lambda r: httpx.Response(200, json={"ok": True}, headers={"content-type": "application/json"})
    )
    items = await http_request_node.run(
        {"method": "GET", "url": "https://api.example.com/x"},
        input_items=[],
        context={},
        transport=transport,
    )
    assert len(items) == 1
    assert items[0].json["status"] == 200
    assert items[0].json["json"] == {"ok": True}
