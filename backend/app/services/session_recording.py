"""Optional per-run browser session recording (MP4 or frame manifest)."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.settings import settings


logger = logging.getLogger(__name__)

_recorders: dict[str, "SessionRecorder"] = {}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _Frame:
    ts: str
    seq: int
    width: int
    height: int
    data: str  # base64 JPEG


@dataclass
class SessionRecorder:
    run_id: str
    frames: list[_Frame] = field(default_factory=list)
    _screencast_active: bool = False
    _cdp: Any = None
    _seq: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def start(self) -> None:
        from app.services.browser_visual import skip_optional_page_screenshots

        if skip_optional_page_screenshots():
            logger.debug(
                "session recording: headed mode — screencast disabled run=%s",
                self.run_id,
            )
            return
        from app.tools.browser import get_active_page

        page = get_active_page(self.run_id)
        if page is None:
            logger.debug("session recording: no active page run=%s", self.run_id)
            return
        try:
            cdp = await page.context.new_cdp_session(page)
            self._cdp = cdp
            every_nth = max(1, round(60 / max(settings.stream_fps, 1)))

            def on_screencast_frame(params: dict[str, Any]) -> None:
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._handle_frame(params))
                except RuntimeError:
                    from app.services import runs as run_svc

                    if run_svc._main_loop is not None:
                        run_svc._main_loop.call_soon_threadsafe(
                            lambda p=params: run_svc._main_loop.create_task(  # type: ignore[union-attr]
                                self._handle_frame(p)
                            )
                        )

            cdp.on("Page.screencastFrame", on_screencast_frame)
            await cdp.send(
                "Page.startScreencast",
                {
                    "format": "jpeg",
                    "quality": settings.stream_jpeg_quality,
                    "maxWidth": settings.stream_max_width,
                    "maxHeight": settings.stream_max_width,
                    "everyNthFrame": every_nth,
                },
            )
            self._screencast_active = True
            logger.debug("session recording screencast started run=%s", self.run_id)
        except Exception:
            logger.exception("session recording start failed run=%s", self.run_id)

    async def _handle_frame(self, params: dict[str, Any]) -> None:
        session_id = params.get("sessionId")
        if self._cdp is not None and session_id is not None:
            try:
                await self._cdp.send(
                    "Page.screencastFrameAck", {"sessionId": session_id}
                )
            except Exception:
                pass

        metadata = params.get("metadata") or {}
        self._seq += 1
        async with self._lock:
            self.frames.append(
                _Frame(
                    ts=_utcnow_iso(),
                    seq=self._seq,
                    width=int(metadata.get("deviceWidth") or 0),
                    height=int(metadata.get("deviceHeight") or 0),
                    data=params.get("data") or "",
                )
            )

    async def inject_frame(
        self,
        data: str,
        *,
        width: int = 800,
        height: int = 600,
    ) -> None:
        """Push a frame without CDP (tests)."""
        self._seq += 1
        async with self._lock:
            self.frames.append(
                _Frame(
                    ts=_utcnow_iso(),
                    seq=self._seq,
                    width=width,
                    height=height,
                    data=data,
                )
            )

    async def stop(self) -> list[_Frame]:
        if self._screencast_active and self._cdp is not None:
            try:
                await self._cdp.send("Page.stopScreencast")
            except Exception:
                pass
            try:
                await self._cdp.detach()
            except Exception:
                pass
            self._cdp = None
        self._screencast_active = False
        async with self._lock:
            return list(self.frames)


def is_enabled(record_video: Optional[bool]) -> bool:
    """Resolve per-run override against global ``video_recording_enabled``."""
    if record_video is False:
        return False
    if record_video is True:
        return True
    return settings.video_recording_enabled


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def mux_frames_to_mp4(frames: list[_Frame], *, fps: int) -> Optional[bytes]:
    """Mux JPEG screencast frames to MP4 via ffmpeg; returns None on failure."""
    if not frames:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for idx, frame in enumerate(frames, start=1):
            try:
                raw = base64.b64decode(frame.data)
            except Exception:
                continue
            if not raw:
                continue
            (tmp_path / f"frame_{idx:04d}.jpg").write_bytes(raw)
        jpgs = sorted(tmp_path.glob("frame_*.jpg"))
        if not jpgs:
            return None
        out_file = tmp_path / "recording.mp4"
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-framerate",
            str(max(fps, 1)),
            "-i",
            str(tmp_path / "frame_%04d.jpg"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(out_file),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            logger.debug("ffmpeg mux failed run frames=%s", len(jpgs), exc_info=True)
            return None
        if not out_file.is_file():
            return None
        return out_file.read_bytes()


def build_frame_manifest(frames: list[_Frame], *, fps: int) -> bytes:
    payload = {
        "format": "frame_manifest",
        "version": 1,
        "fps": fps,
        "frames": [
            {
                "ts": f.ts,
                "seq": f.seq,
                "width": f.width,
                "height": f.height,
                "data": f.data,
            }
            for f in frames
        ],
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


async def start_recording(run_id: str) -> None:
    if not run_id or run_id == "__legacy__":
        return
    recorder = SessionRecorder(run_id=run_id)
    _recorders[run_id] = recorder
    await recorder.start()


async def finalize_recording(run_id: str) -> None:
    """Stop screencast while the page is alive, then persist a recording artifact."""
    recorder = _recorders.pop(run_id, None)
    if recorder is None:
        return

    frames = await recorder.stop()
    if not frames:
        return

    from app.services import artifacts as artifact_svc

    fps = max(settings.stream_fps, 1)
    mp4: Optional[bytes] = None
    if ffmpeg_available():
        mp4 = mux_frames_to_mp4(frames, fps=fps)

    if mp4:
        artifact_svc.store_bytes(
            run_id,
            "recording",
            mp4,
            content_type="video/mp4",
            filename="session.mp4",
        )
        return

    manifest = build_frame_manifest(frames, fps=fps)
    artifact_svc.store_bytes(
        run_id,
        "recording",
        manifest,
        content_type="application/json",
        filename="session-manifest.json",
        note="ffmpeg unavailable; frame manifest playback",
    )


def clear_recording(run_id: str) -> None:
    """Drop in-memory recorder state (tests / teardown)."""
    _recorders.pop(run_id, None)


def reset_for_tests() -> None:
    _recorders.clear()


__all__ = [
    "SessionRecorder",
    "build_frame_manifest",
    "clear_recording",
    "ffmpeg_available",
    "finalize_recording",
    "is_enabled",
    "mux_frames_to_mp4",
    "reset_for_tests",
    "start_recording",
]
