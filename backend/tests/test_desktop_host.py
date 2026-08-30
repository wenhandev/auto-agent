"""Integration tests for desktop-host IPC server."""

from __future__ import annotations

import asyncio

import pytest

from app.worker.desktop_api import DesktopApi
from app.worker.desktop_host import _serve_ipc_uds
from app.worker.desktop_protocol import RequestEnvelope, decode_response_frame, encode_frame
from app.worker.desktop_runtime import DesktopRuntime


@pytest.mark.asyncio
async def test_ipc_server_health() -> None:
    uds = "/tmp/auto-agent-test-ipc.sock"
    runtime = DesktopRuntime(
        approval_status="approved",
        logged_in=True,
        environment={"environment_status": "ready", "checks": []},
    )
    api = DesktopApi(runtime)

    server_task = asyncio.create_task(_serve_ipc_uds(api, uds))
    await asyncio.sleep(0.05)

    try:
        reader, writer = await asyncio.open_unix_connection(uds)
        request = RequestEnvelope(id="t1", method="health", params={})
        writer.write(encode_frame(request))
        await writer.drain()

        header = await reader.readexactly(4)
        length = int.from_bytes(header, "big")
        body = await reader.readexactly(length)
        response = decode_response_frame(header + body)
        assert response.ok is True
        assert response.result == {"status": "ok"}

        writer.close()
        await writer.wait_closed()
    finally:
        server_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await server_task
