"""Auto-capture browser downloads and optional HAR recording per run."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Optional

from playwright.async_api import BrowserContext, Download, Page

from app.services import artifacts as artifact_svc
from app.settings import settings


logger = logging.getLogger(__name__)

_har_paths: dict[str, Path] = {}
_download_attached: set[str] = set()


def prepare_har_context_option(run_id: str) -> dict[str, str]:
    """Return Playwright context kwargs to record a HAR when enabled."""
    if not settings.har_enabled or not run_id or run_id == "__legacy__":
        return {}
    tmp = tempfile.NamedTemporaryFile(suffix=".har", delete=False)
    path = Path(tmp.name)
    tmp.close()
    _har_paths[run_id] = path
    return {"record_har_path": str(path)}


def pop_har_path(run_id: str) -> Optional[Path]:
    return _har_paths.pop(run_id, None)


def attach_download_listener(run_id: str, page: Page) -> None:
    """Register page.on('download') once per run to store download artifacts."""
    if not run_id or run_id == "__legacy__" or run_id in _download_attached:
        return
    page_on = getattr(page, "on", None)
    if not callable(page_on):
        return
    _download_attached.add(run_id)

    def _schedule(download: Download) -> None:
        asyncio.create_task(_capture_download(run_id, download))

    page_on("download", _schedule)


async def _capture_download(run_id: str, download: Download) -> None:
    try:
        path = await download.path()
        if path is None:
            return
        data = Path(path).read_bytes()
        filename = download.suggested_filename or "download.bin"
        artifact_svc.store_bytes(
            run_id,
            "download",
            data,
            filename=filename,
        )
    except Exception:
        logger.debug("browser download capture failed run=%s", run_id, exc_info=True)


def persist_har_artifact(run_id: str, har_path: Path) -> None:
    """Read a flushed HAR file and store it as a run artifact."""
    try:
        if not har_path.is_file():
            return
        data = har_path.read_bytes()
        if not data:
            return
        artifact_svc.store_bytes(
            run_id,
            "har",
            data,
            filename="network.har",
            content_type="application/json",
        )
    except Exception:
        logger.debug("HAR artifact persist failed run=%s", run_id, exc_info=True)
    finally:
        try:
            har_path.unlink(missing_ok=True)
        except OSError:
            pass


async def finalize_har_after_context_close(run_id: str) -> None:
    """Persist HAR bytes after the browser context has been closed."""
    har_path = pop_har_path(run_id)
    if har_path is None:
        return
    persist_har_artifact(run_id, har_path)


def clear_run_capture(run_id: str) -> None:
    """Drop per-run capture bookkeeping (tests / run teardown)."""
    _download_attached.discard(run_id)
    path = _har_paths.pop(run_id, None)
    if path is not None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def reset_for_tests() -> None:
    _har_paths.clear()
    _download_attached.clear()


__all__ = [
    "attach_download_listener",
    "clear_run_capture",
    "finalize_har_after_context_close",
    "persist_har_artifact",
    "pop_har_path",
    "prepare_har_context_option",
    "reset_for_tests",
]
