"""Per-workflow selector / vision-plan cache with URL-pattern keys."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlmodel import Session, delete, select

from app.db.models import SelectorCache
from app.settings import settings


logger = logging.getLogger(__name__)

_NUMERIC_SEGMENT = re.compile(r"^\d+$")
_VOLATILE_QUERY_PREFIXES = ("utm_", "session", "sid", "token", "_", "fbclid", "gclid")
_VOLATILE_QUERY_EXACT = frozenset({"id", "ref", "timestamp", "ts", "nonce"})

CacheKind = Literal["selector", "vision"]


@dataclass(frozen=True)
class CacheLookup:
    entry: SelectorCache
    url_pattern: str


@dataclass(frozen=True)
class CacheStats:
    workflow_id: str
    entry_count: int
    total_hits: int
    total_misses: int
    entries: list[dict[str, Any]]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalizer_mode(node_params: Optional[dict[str, Any]]) -> str:
    mode = (node_params or {}).get("cache_url_normalizer", "default")
    if mode not in ("default", "strict", "path_only"):
        return "default"
    return str(mode)


def _normalize_path(path: str) -> str:
    if not path or path == "/":
        return "/"
    segments = path.split("/")
    out: list[str] = []
    for seg in segments:
        if not seg:
            out.append(seg)
            continue
        if _NUMERIC_SEGMENT.match(seg):
            out.append("{id}")
        else:
            out.append(seg)
    normalized = "/".join(out)
    return normalized if normalized.startswith("/") else f"/{normalized}"


def _drop_volatile_query(query: str) -> str:
    if not query:
        return ""
    kept: list[tuple[str, str]] = []
    for key, value in parse_qsl(query, keep_blank_values=True):
        lower = key.lower()
        if lower in _VOLATILE_QUERY_EXACT:
            continue
        if any(lower.startswith(prefix) for prefix in _VOLATILE_QUERY_PREFIXES):
            continue
        kept.append((key, value))
    return urlencode(kept)


def normalize_url(url: str, node_params: Optional[dict[str, Any]] = None) -> str:
    """Map a live page URL to a cache key pattern."""
    mode = _normalizer_mode(node_params)
    if mode == "strict":
        return url

    parsed = urlparse(url)
    path = parsed.path or "/"
    if mode in ("default", "path_only"):
        path = _normalize_path(path)

    query = ""
    if mode == "default":
        query = _drop_volatile_query(parsed.query)

    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        path,
        parsed.params,
        query,
        "",
    ))  # drop fragment


def is_cache_enabled(session: Optional[Session]) -> bool:
    from app.services.llm_runtime import get_selector_cache_settings

    try:
        return bool(get_selector_cache_settings(session).enabled)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("selector-cache: settings lookup failed (%s)", exc)
        return True


def _is_expired(entry: SelectorCache) -> bool:
    ttl_days = max(1, int(settings.cache_ttl_days))
    cutoff = _utcnow() - timedelta(days=ttl_days)
    last = entry.last_success_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return last < cutoff


def get_entry(
    session: Session,
    *,
    workflow_id: str,
    node_id: str,
    url: str,
    node_params: Optional[dict[str, Any]] = None,
) -> Optional[CacheLookup]:
    pattern = normalize_url(url, node_params)
    entry = session.exec(
        select(SelectorCache).where(
            SelectorCache.workflow_id == workflow_id,
            SelectorCache.node_id == node_id,
            SelectorCache.url_pattern == pattern,
        )
    ).first()
    if entry is None:
        return None
    if _is_expired(entry):
        session.delete(entry)
        session.commit()
        return None
    return CacheLookup(entry=entry, url_pattern=pattern)


def record_hit(session: Session, entry: SelectorCache) -> None:
    entry.hit_count += 1
    entry.consecutive_misses = 0
    entry.last_success_at = _utcnow()
    entry.updated_at = _utcnow()
    session.add(entry)
    session.commit()
    session.refresh(entry)


def record_miss(session: Session, entry: SelectorCache) -> bool:
    """Increment miss counters; evict when threshold reached. Returns True if evicted."""
    entry.miss_count += 1
    entry.consecutive_misses += 1
    entry.updated_at = _utcnow()
    max_misses = max(1, int(settings.cache_max_misses))
    if entry.consecutive_misses >= max_misses:
        session.delete(entry)
        session.commit()
        return True
    session.add(entry)
    session.commit()
    return False


def upsert_success(
    session: Session,
    *,
    workflow_id: str,
    node_id: str,
    url: str,
    selector: str,
    confidence: float,
    kind: CacheKind = "selector",
    plan: Optional[dict[str, Any]] = None,
    node_params: Optional[dict[str, Any]] = None,
) -> SelectorCache:
    pattern = normalize_url(url, node_params)
    entry = session.exec(
        select(SelectorCache).where(
            SelectorCache.workflow_id == workflow_id,
            SelectorCache.node_id == node_id,
            SelectorCache.url_pattern == pattern,
        )
    ).first()
    now = _utcnow()
    conf = max(0.0, min(1.0, float(confidence)))
    plan_json = json.dumps(plan, ensure_ascii=False) if plan else None
    if entry is None:
        entry = SelectorCache(
            workflow_id=workflow_id,
            node_id=node_id,
            url_pattern=pattern,
            selector=selector,
            kind=kind,
            confidence=conf,
            plan_json=plan_json,
            last_success_at=now,
            hit_count=0,
            miss_count=0,
            consecutive_misses=0,
            created_at=now,
            updated_at=now,
        )
    else:
        entry.selector = selector
        entry.kind = kind
        entry.confidence = conf
        entry.plan_json = plan_json
        entry.last_success_at = now
        entry.consecutive_misses = 0
        entry.updated_at = now
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def clear_workflow_cache(session: Session, workflow_id: str) -> int:
    rows = session.exec(
        select(SelectorCache).where(SelectorCache.workflow_id == workflow_id)
    ).all()
    count = len(rows)
    if count:
        session.exec(delete(SelectorCache).where(SelectorCache.workflow_id == workflow_id))
        session.commit()
    return count


def get_cache_stats(session: Session, workflow_id: str) -> CacheStats:
    rows = session.exec(
        select(SelectorCache)
        .where(SelectorCache.workflow_id == workflow_id)
        .order_by(SelectorCache.updated_at.desc())  # type: ignore[attr-defined]
    ).all()
    entries: list[dict[str, Any]] = []
    total_hits = 0
    total_misses = 0
    for row in rows:
        total_hits += row.hit_count
        total_misses += row.miss_count
        entries.append({
            "id": row.id,
            "node_id": row.node_id,
            "url_pattern": row.url_pattern,
            "selector": row.selector,
            "kind": row.kind,
            "confidence": row.confidence,
            "hit_count": row.hit_count,
            "miss_count": row.miss_count,
            "consecutive_misses": row.consecutive_misses,
            "last_success_at": row.last_success_at.isoformat(),
        })
    return CacheStats(
        workflow_id=workflow_id,
        entry_count=len(rows),
        total_hits=total_hits,
        total_misses=total_misses,
        entries=entries,
    )


def parse_vision_plan(entry: SelectorCache) -> Optional[dict[str, Any]]:
    if not entry.plan_json:
        return None
    try:
        return json.loads(entry.plan_json)
    except json.JSONDecodeError:
        return None


__all__ = [
    "CacheKind",
    "CacheLookup",
    "CacheStats",
    "clear_workflow_cache",
    "get_cache_stats",
    "get_entry",
    "is_cache_enabled",
    "normalize_url",
    "parse_vision_plan",
    "record_hit",
    "record_miss",
    "upsert_success",
]
