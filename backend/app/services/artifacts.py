"""Durable run artifact store: files on disk + RunArtifact index rows."""

from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, BinaryIO, Optional

from sqlmodel import Session, select

from app.db.models import RunArtifact
from app.db.session import engine
from app.services import artifact_context
from app.settings import settings


logger = logging.getLogger(__name__)

ARTIFACT_KINDS = frozenset({
    "screenshot",
    "recording",
    "trace",
    "llm_trace",
    "download",
    "har",
})

_KIND_EXTENSIONS: dict[str, str] = {
    "screenshot": ".png",
    "recording": ".mp4",
    "trace": ".zip",
    "llm_trace": ".json",
    "download": ".bin",
    "har": ".har",
}

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_default_root = _BACKEND_ROOT / "data" / "artifacts"
_artifact_root: Path = _default_root
_seq_counters: dict[str, int] = {}


def set_artifact_root(path: Path) -> None:
    """Override artifact root (tests)."""
    global _artifact_root
    _artifact_root = path


def get_artifact_root() -> Path:
    return _artifact_root


def ensure_artifact_root() -> Path:
    _artifact_root.mkdir(parents=True, exist_ok=True)
    return _artifact_root


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:32]


def _next_seq(run_id: str, kind: str) -> int:
    key = f"{run_id}:{kind}"
    n = _seq_counters.get(key, 0)
    _seq_counters[key] = n + 1
    return n


def _guess_content_type(kind: str, filename: str) -> str:
    if kind == "screenshot":
        return "image/png"
    if kind == "recording":
        return "video/mp4"
    if kind == "trace":
        return "application/zip"
    if kind == "llm_trace":
        return "application/json"
    if kind == "har":
        return "application/json"
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def _run_dir(run_id: str, kind: str) -> Path:
    return _artifact_root / run_id / kind


def _find_dedupe(
    session: Session,
    run_id: str,
    content_hash: str,
) -> Optional[RunArtifact]:
    row = session.exec(
        select(RunArtifact).where(
            RunArtifact.run_id == run_id,
            RunArtifact.content_hash == content_hash,
            RunArtifact.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    ).first()
    return row


def store_bytes(
    run_id: str,
    kind: str,
    data: bytes,
    *,
    content_type: Optional[str] = None,
    node_id: Optional[str] = None,
    step_index: Optional[int] = None,
    filename: Optional[str] = None,
    note: Optional[str] = None,
    session: Optional[Session] = None,
) -> RunArtifact:
    """Persist bytes as a run artifact; dedupe identical content within a run."""
    if kind not in ARTIFACT_KINDS:
        raise ValueError(f"unknown artifact kind: {kind!r}")

    if len(data) > settings.max_artifact_bytes:
        note = note or "过大未内联"
        data = b""

    content_hash = _content_hash(data) if data else None
    own_session = session is None
    sess = session or Session(engine)
    try:
        if content_hash and data:
            existing = _find_dedupe(sess, run_id, content_hash)
            if existing is not None:
                return existing

        ext = _KIND_EXTENSIONS.get(kind, ".bin")
        if filename and "." in filename:
            ext = Path(filename).suffix or ext

        seq = _next_seq(run_id, kind)
        rel_name = f"{seq:04d}{ext}"
        dest_dir = _run_dir(run_id, kind)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / rel_name
        if data:
            dest_path.write_bytes(data)

        rel_path = str(Path(run_id) / kind / rel_name)
        ct = content_type or _guess_content_type(kind, rel_name)
        row = RunArtifact(
            run_id=run_id,
            kind=kind,
            path=rel_path,
            content_type=ct,
            bytes=len(data),
            node_id=node_id or artifact_context.get_node_id(),
            step_index=step_index if step_index is not None else artifact_context.get_step_index(),
            content_hash=content_hash,
            filename=filename,
            note=note,
        )
        sess.add(row)
        if own_session:
            sess.commit()
            sess.refresh(row)
        return row
    finally:
        if own_session:
            sess.close()


def store_screenshot(
    run_id: str,
    data: bytes,
    *,
    node_id: Optional[str] = None,
    step_index: Optional[int] = None,
    session: Optional[Session] = None,
) -> RunArtifact:
    return store_bytes(
        run_id,
        "screenshot",
        data,
        content_type="image/png",
        node_id=node_id,
        step_index=step_index,
        session=session,
    )


def store_from_path(
    run_id: str,
    kind: str,
    source: str | Path,
    *,
    node_id: Optional[str] = None,
    step_index: Optional[int] = None,
    filename: Optional[str] = None,
    session: Optional[Session] = None,
) -> Optional[RunArtifact]:
    """Read a file path and store as artifact; returns None if missing."""
    path = Path(source)
    if not path.is_file():
        return None
    data = path.read_bytes()
    return store_bytes(
        run_id,
        kind,
        data,
        node_id=node_id,
        step_index=step_index,
        filename=filename or path.name,
        session=session,
    )


def store_llm_trace_json(
    run_id: str,
    payload: dict[str, Any],
    *,
    node_id: Optional[str] = None,
    step_index: Optional[int] = None,
    session: Optional[Session] = None,
) -> RunArtifact:
    data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    return store_bytes(
        run_id,
        "llm_trace",
        data,
        content_type="application/json",
        node_id=node_id,
        step_index=step_index,
        session=session,
    )


def store_trace_json(
    run_id: str,
    payload: dict[str, Any],
    *,
    node_id: Optional[str] = None,
    step_index: Optional[int] = None,
    session: Optional[Session] = None,
) -> RunArtifact:
    """Backward-compatible alias for LLM trace JSON artifacts."""
    return store_llm_trace_json(
        run_id,
        payload,
        node_id=node_id,
        step_index=step_index,
        session=session,
    )


def resolve_path(artifact: RunArtifact) -> Path:
    return _artifact_root / artifact.path


def list_artifacts(
    run_id: str,
    *,
    kind: Optional[str] = None,
    node_id: Optional[str] = None,
    session: Optional[Session] = None,
) -> list[RunArtifact]:
    own_session = session is None
    sess = session or Session(engine)
    try:
        stmt = select(RunArtifact).where(RunArtifact.run_id == run_id)
        if kind:
            stmt = stmt.where(RunArtifact.kind == kind)
        if node_id:
            stmt = stmt.where(RunArtifact.node_id == node_id)
        stmt = stmt.order_by(RunArtifact.created_at)  # type: ignore[attr-defined]
        return list(sess.exec(stmt).all())
    finally:
        if own_session:
            sess.close()


def get_artifact(
    artifact_id: str,
    *,
    run_id: Optional[str] = None,
    session: Optional[Session] = None,
) -> Optional[RunArtifact]:
    own_session = session is None
    sess = session or Session(engine)
    try:
        row = sess.get(RunArtifact, artifact_id)
        if row is None:
            return None
        if run_id is not None and row.run_id != run_id:
            return None
        return row
    finally:
        if own_session:
            sess.close()


def count_by_kind(run_id: str, session: Optional[Session] = None) -> dict[str, int]:
    rows = list_artifacts(run_id, session=session)
    counts: dict[str, int] = {k: 0 for k in ARTIFACT_KINDS}
    for row in rows:
        if row.deleted_at is None:
            counts[row.kind] = counts.get(row.kind, 0) + 1
    return {k: v for k, v in counts.items() if v > 0}


async def enrich_event_payload(
    run_id: str,
    payload: dict[str, Any],
    *,
    session: Optional[Session] = None,
) -> dict[str, Any]:
    """Attach durable artifact_id for vision_step / node events with screenshots."""
    event = payload.get("event")
    if event not in ("vision_step", "node_started", "node_completed"):
        return payload

    screenshot_ref = payload.get("screenshot_ref")
    if not screenshot_ref:
        return payload

    own_session = session is None
    sess = session or Session(engine)
    try:
        artifact = store_from_path(
            run_id,
            "screenshot",
            screenshot_ref,
            node_id=payload.get("node_id"),
            step_index=payload.get("step_index"),
            session=sess,
        )
        if artifact is None:
            return payload
        enriched = {**payload, "artifact_id": artifact.id}
        if own_session:
            sess.commit()
        return enriched
    finally:
        if own_session:
            sess.close()


async def capture_page_screenshot(
    run_id: str,
    *,
    node_id: Optional[str] = None,
    phase: str = "capture",
) -> Optional[str]:
    """Best-effort page screenshot; returns artifact_id or None."""
    from app.services.browser_visual import skip_optional_page_screenshots

    if skip_optional_page_screenshots():
        return None
    try:
        from app.tools.browser import get_page

        page = await get_page()
        data = await page.screenshot(full_page=False, type="png")
        row = store_screenshot(run_id, data, node_id=node_id)
        return row.id
    except Exception:
        logger.debug("capture_page_screenshot failed run=%s phase=%s", run_id, phase)
        return None


def reap_expired_artifacts() -> int:
    """Delete files older than retention window; tombstone index rows."""
    cutoff = _utcnow() - timedelta(days=settings.artifact_retention_days)
    removed = 0
    with Session(engine) as session:
        rows = session.exec(
            select(RunArtifact).where(
                RunArtifact.deleted_at.is_(None),  # type: ignore[union-attr]
                RunArtifact.created_at < cutoff,
            )
        ).all()
        for row in rows:
            file_path = resolve_path(row)
            if file_path.is_file():
                try:
                    file_path.unlink()
                except OSError:
                    logger.warning("failed to delete artifact file %s", file_path)
            row.deleted_at = _utcnow()
            session.add(row)
            removed += 1
        if removed:
            session.commit()
    if removed:
        logger.info("artifact reaper removed %d expired artifact(s)", removed)
    return removed


def reset_artifact_root() -> None:
    """Restore default artifact root (tests)."""
    global _artifact_root
    _artifact_root = _default_root


def reset_seq_counters() -> None:
    """Clear in-memory sequence counters (tests)."""
    _seq_counters.clear()


__all__ = [
    "ARTIFACT_KINDS",
    "capture_page_screenshot",
    "count_by_kind",
    "enrich_event_payload",
    "ensure_artifact_root",
    "get_artifact",
    "get_artifact_root",
    "list_artifacts",
    "reap_expired_artifacts",
    "reset_artifact_root",
    "reset_seq_counters",
    "resolve_path",
    "set_artifact_root",
    "store_bytes",
    "store_from_path",
    "store_llm_trace_json",
    "store_screenshot",
    "store_trace_json",
]
