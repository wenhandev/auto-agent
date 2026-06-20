"""Recording session management and action trace capture."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from playwright.async_api import Page
from sqlmodel import Session

from app.db.models import BrowserProfile, Recording
from app.services import artifact_context
from app.services import browser_pool
from app.tools import browser as browser_tools

logger = logging.getLogger(__name__)

_SENSITIVE_INPUT_TYPES = frozenset({"password"})
_SENSITIVE_AUTOCOMPLETE = frozenset({"one-time-code", "cc-number", "cc-csc"})
_SENSITIVE_NAME_RE = re.compile(
    r"(password|passwd|pwd|secret|otp|2fa|one.?time|token|pin)",
    re.IGNORECASE,
)

_RECORDING_INIT_SCRIPT = """
(() => {
  if (window.__autoAgentRecording) return;
  window.__autoAgentRecording = { queue: [] };
  const push = (type, detail) => {
    window.__autoAgentRecording.queue.push({
      type,
      ts: Date.now(),
      url: location.href,
      ...detail,
    });
  };
  document.addEventListener('click', (ev) => {
    const el = ev.target && ev.target.closest
      ? ev.target.closest('button,a,input,select,textarea,[role="button"],[role="link"]')
      : ev.target;
    if (!el) return;
    push('click', {
      selector: el.id ? `#${el.id}` : null,
      tag: el.tagName ? el.tagName.toLowerCase() : null,
      role: el.getAttribute('role'),
      name: el.getAttribute('aria-label') || el.getAttribute('name') || el.getAttribute('placeholder') || (el.innerText || '').trim().slice(0, 120),
      input_type: el.getAttribute('type'),
      autocomplete: el.getAttribute('autocomplete'),
    });
  }, true);
  document.addEventListener('input', (ev) => {
    const el = ev.target;
    if (!el || !el.tagName) return;
    const tag = el.tagName.toLowerCase();
    if (tag !== 'input' && tag !== 'textarea') return;
    push('fill', {
      selector: el.id ? `#${el.id}` : null,
      tag,
      role: el.getAttribute('role'),
      name: el.getAttribute('aria-label') || el.getAttribute('name') || el.getAttribute('placeholder') || '',
      input_type: el.getAttribute('type'),
      autocomplete: el.getAttribute('autocomplete'),
      value: el.value,
    });
  }, true);
  document.addEventListener('change', (ev) => {
    const el = ev.target;
    if (!el || el.tagName !== 'SELECT') return;
    push('select', {
      selector: el.id ? `#${el.id}` : null,
      name: el.getAttribute('aria-label') || el.getAttribute('name') || '',
      value: el.value,
    });
  }, true);
})();
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def is_sensitive_field(
    *,
    input_type: Optional[str] = None,
    autocomplete: Optional[str] = None,
    name: Optional[str] = None,
    sensitive: Optional[bool] = None,
) -> bool:
    if sensitive is True:
        return True
    if input_type and input_type.lower() in _SENSITIVE_INPUT_TYPES:
        return True
    if autocomplete and autocomplete.lower() in _SENSITIVE_AUTOCOMPLETE:
        return True
    if name and _SENSITIVE_NAME_RE.search(name):
        return True
    return False


def sanitize_fill_value(
    value: Optional[str],
    *,
    input_type: Optional[str] = None,
    autocomplete: Optional[str] = None,
    name: Optional[str] = None,
    sensitive: Optional[bool] = None,
) -> tuple[Optional[str], bool]:
    """Return (stored_value, is_sensitive). Sensitive values are never stored."""
    if is_sensitive_field(
        input_type=input_type,
        autocomplete=autocomplete,
        name=name,
        sensitive=sensitive,
    ):
        return None, True
    return value, False


@dataclass
class _ActiveRecording:
    recording_id: str
    events: list[dict[str, Any]] = field(default_factory=list)
    page: Optional[Page] = None
    poll_task: Optional[Any] = None
    nav_handler: Optional[Any] = None


_active: dict[str, _ActiveRecording] = {}


def _next_seq(events: list[dict[str, Any]]) -> int:
    if not events:
        return 0
    return max(int(e.get("seq", 0)) for e in events) + 1


def _normalize_raw_event(raw: dict[str, Any], seq: int) -> dict[str, Any]:
    event_type = str(raw.get("type") or "unknown")
    stored_value: Optional[str] = None
    sensitive = False
    if event_type == "fill":
        stored_value, sensitive = sanitize_fill_value(
            raw.get("value"),
            input_type=raw.get("input_type"),
            autocomplete=raw.get("autocomplete"),
            name=raw.get("name"),
            sensitive=raw.get("sensitive"),
        )
    event: dict[str, Any] = {
        "seq": seq,
        "type": event_type,
        "ts": raw.get("ts") or _utcnow().isoformat(),
        "url": raw.get("url"),
        "selector": raw.get("selector"),
        "element_index": raw.get("element_index"),
        "description": raw.get("description") or raw.get("name"),
        "tag": raw.get("tag"),
        "role": raw.get("role"),
        "input_type": raw.get("input_type"),
        "autocomplete": raw.get("autocomplete"),
        "screenshot_ref": raw.get("screenshot_ref"),
        "sensitive": sensitive or bool(raw.get("sensitive")),
    }
    if event_type == "fill" and not event["sensitive"]:
        event["value"] = stored_value
    if event_type == "select" and not event["sensitive"]:
        event["value"] = raw.get("value")
    if event_type == "navigate":
        event["url"] = raw.get("url")
    return event


def append_event(recording_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Append a normalized event to an active or persisted recording buffer."""
    active = _active.get(recording_id)
    if active is not None:
        seq = _next_seq(active.events)
        event = _normalize_raw_event(raw, seq)
        active.events.append(event)
        return event
    raise KeyError(f"recording {recording_id!r} is not active")


def get_active_events(recording_id: str) -> list[dict[str, Any]]:
    active = _active.get(recording_id)
    if active is None:
        return []
    return list(active.events)


async def _poll_dom_queue(active: _ActiveRecording) -> None:
    import asyncio

    page = active.page
    if page is None:
        return
    while active.recording_id in _active:
        try:
            queue = await page.evaluate(
                "() => { const q = window.__autoAgentRecording?.queue || []; "
                "window.__autoAgentRecording.queue = []; return q; }"
            )
            for raw in queue or []:
                append_event(active.recording_id, raw)
        except Exception as exc:
            logger.debug("recording poll stopped for %s: %s", active.recording_id, exc)
            break
        await asyncio.sleep(0.25)


async def _attach_page_listeners(active: _ActiveRecording) -> None:
    import asyncio

    page = active.page
    if page is None:
        return

    await page.add_init_script(_RECORDING_INIT_SCRIPT)

    def on_nav(frame: Any) -> None:
        if frame != page.main_frame:
            return
        try:
            append_event(
                active.recording_id,
                {"type": "navigate", "url": frame.url, "ts": _utcnow().isoformat()},
            )
        except Exception:
            pass

    page.on("framenavigated", on_nav)
    active.nav_handler = on_nav
    active.poll_task = asyncio.create_task(_poll_dom_queue(active))


async def start_recording(
    session: Session,
    *,
    browser_profile_id: Optional[str] = None,
    start_url: Optional[str] = None,
    name: Optional[str] = None,
    acquire_browser: bool = True,
) -> Recording:
    if browser_profile_id:
        profile = session.get(BrowserProfile, browser_profile_id)
        if profile is None:
            raise ValueError("browser profile not found")

    recording = Recording(
        name=name or f"Recording {uuid4().hex[:8]}",
        status="active",
        browser_profile_id=browser_profile_id,
        start_url=start_url,
        events_json="[]",
        created_at=_utcnow(),
        started_at=_utcnow(),
    )
    session.add(recording)
    session.commit()
    session.refresh(recording)

    active = _ActiveRecording(recording_id=recording.id)
    _active[recording.id] = active

    if acquire_browser:
        artifact_context.set_run_context(recording.id)
        try:
            await browser_tools.begin_run(browser_profile_id, run_id=recording.id)
            page = browser_pool.get_page(recording.id)
            active.page = page
            if start_url and page is not None:
                await page.goto(start_url, wait_until="domcontentloaded")
                append_event(
                    recording.id,
                    {
                        "type": "navigate",
                        "url": start_url,
                        "ts": _utcnow().isoformat(),
                    },
                )
            if page is not None:
                await _attach_page_listeners(active)
        except Exception:
            await stop_recording(session, recording.id, release_browser=False)
            raise

    return recording


async def stop_recording(
    session: Session,
    recording_id: str,
    *,
    release_browser: bool = True,
) -> Recording:
    recording = session.get(Recording, recording_id)
    if recording is None:
        raise ValueError("recording not found")
    if recording.status != "active":
        raise ValueError("recording is not active")

    active = _active.pop(recording_id, None)
    events: list[dict[str, Any]] = []
    if active is not None:
        if active.poll_task is not None:
            active.poll_task.cancel()
            try:
                import asyncio

                await active.poll_task
            except Exception:
                pass
        events = list(active.events)
        if release_browser:
            try:
                await browser_tools.end_run(run_id=recording_id)
            except Exception as exc:
                logger.warning("failed to release browser for recording %s: %s", recording_id, exc)
            artifact_context.clear_run_context()

    recording.events_json = json.dumps(events, ensure_ascii=False)
    recording.status = "stopped"
    recording.stopped_at = _utcnow()
    session.add(recording)
    session.commit()
    session.refresh(recording)
    return recording


def load_events(recording: Recording) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(recording.events_json or "[]")
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return parsed


def ingest_events(
    session: Session,
    recording_id: str,
    raw_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Append events to an active recording (used by API/tests)."""
    if recording_id not in _active:
        raise ValueError("recording is not active")
    out: list[dict[str, Any]] = []
    for raw in raw_events:
        out.append(append_event(recording_id, raw))
    return out


__all__ = [
    "append_event",
    "get_active_events",
    "ingest_events",
    "is_sensitive_field",
    "load_events",
    "sanitize_fill_value",
    "start_recording",
    "stop_recording",
]
