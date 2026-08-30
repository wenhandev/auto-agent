"""Desktop runtime message host — framed JSON IPC + optional stream HTTP (Phase 4B)."""

from __future__ import annotations

import asyncio
import logging
import struct
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.worker.desktop_api import DesktopApi, DesktopApiError, sse_event_line
from app.worker.desktop_protocol import decode_request_frame, dispatch, encode_frame
from app.worker.desktop_runtime import DesktopRuntime, start_background_tasks, stop_background_tasks


logger = logging.getLogger(__name__)


def create_stream_app(runtime: DesktopRuntime, api: DesktopApi) -> FastAPI:
    """Minimal HTTP surface for SSE/WS relays until streams move to the message protocol."""
    app = FastAPI(title="Auto Agent Desktop Stream Relay")

    @app.get("/health")
    def health() -> dict[str, str]:
        return api.health()

    @app.get("/runs/{run_id}/events")
    async def run_events(run_id: str) -> StreamingResponse:
        try:

            async def event_stream():
                async for payload in api.iter_run_events(run_id):
                    line = sse_event_line(payload)
                    if line:
                        yield line

            return StreamingResponse(
                event_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        except DesktopApiError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.message) from exc

    @app.websocket("/ws/stream/{run_id}")
    async def ws_stream(run_id: str, ws: WebSocket) -> None:
        await ws.accept()
        if runtime.runs.get_run(run_id) is None:
            await ws.close(code=4404)
            return
        viewers = runtime._stream_viewers.setdefault(run_id, set())
        viewers.add(ws)
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=64)
        runtime.runs._subscribers.setdefault(run_id, []).append(queue)
        try:
            while True:
                payload = await queue.get()
                if payload is None:
                    await ws.send_json({"type": "stream_ended"})
                    break
                if payload.get("type") == "stream_frame":
                    await ws.send_json({
                        "type": "frame",
                        "seq": payload.get("seq"),
                        "data": payload.get("data"),
                        "width": payload.get("width"),
                        "height": payload.get("height"),
                        "ts": payload.get("ts"),
                    })
        except WebSocketDisconnect:
            pass
        finally:
            viewers.discard(ws)
            subs = runtime.runs._subscribers.get(run_id, [])
            if queue in subs:
                subs.remove(queue)

    return app


async def _handle_ipc_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    api: DesktopApi,
) -> None:
    peer = writer.get_extra_info("peername")
    try:
        while True:
            header = await reader.readexactly(4)
            (length,) = struct.unpack(">I", header)
            body = await reader.readexactly(length)
            request = decode_request_frame(header + body)
            response = await dispatch(api, request)
            frame = encode_frame(response)
            writer.write(frame)
            await writer.drain()
    except asyncio.IncompleteReadError:
        pass
    except Exception as exc:
        logger.warning("ipc client %s error: %s", peer, exc)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def _serve_stream_uds(app: FastAPI, uds: str) -> None:
    path = Path(uds)
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    config = uvicorn.Config(app, uds=uds, log_level="info")
    server = uvicorn.Server(config)
    logger.info("desktop stream relay listening on unix:%s", uds)
    await server.serve()


async def _serve_ipc_uds(api: DesktopApi, uds: str) -> None:
    path = Path(uds)
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)

    async def on_client(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        await _handle_ipc_client(reader, writer, api)

    server = await asyncio.start_unix_server(on_client, path=uds)
    logger.info("desktop runtime IPC listening on unix:%s", uds)
    async with server:
        await server.serve_forever()


async def run_desktop_host(*, ipc_uds: str, stream_uds: str | None = None) -> None:
    runtime = DesktopRuntime()
    runtime.refresh_credentials()
    api = DesktopApi(runtime)
    await start_background_tasks(runtime)

    tasks: list[asyncio.Task[None]] = []
    try:
        if stream_uds:
            stream_app = create_stream_app(runtime, api)
            tasks.append(asyncio.create_task(_serve_stream_uds(stream_app, stream_uds)))
        tasks.append(asyncio.create_task(_serve_ipc_uds(api, ipc_uds)))
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        await stop_background_tasks(runtime)


def run_desktop_host_sync(*, ipc_uds: str, stream_uds: str | None = None) -> None:
    asyncio.run(run_desktop_host(ipc_uds=ipc_uds, stream_uds=stream_uds))
