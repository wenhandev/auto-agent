"""Poll trigger runner: list operation → dedup → enqueue runs."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from sqlmodel import Session

from app.db.models import Trigger
from app.db.session import engine
from app.integrations.json_path import resolve_path
from app.integrations.registry import resolve_operation
from app.nodes import integration as integration_node
from app.services import runs as run_svc

logger = logging.getLogger(__name__)

_SEEN_KEYS_CAP = 500


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_seen_keys(raw: Optional[str]) -> set[str]:
    if not raw:
        return set()
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return {str(x) for x in data}
    except Exception:
        pass
    return set()


def _dump_seen_keys(seen: set[str]) -> str:
    trimmed = sorted(seen)[-_SEEN_KEYS_CAP:]
    return json.dumps(trimmed, ensure_ascii=False)


def _dedup_key(record: dict[str, Any], path: str) -> str:
    return str(resolve_path(record, path))


def _key_gt(a: str, b: Optional[str]) -> bool:
    if b is None:
        return True
    try:
        return float(a) > float(b)
    except ValueError:
        return a > b


def _record_summary(record: dict[str, Any], dedup_path: str) -> str:
    try:
        key = _dedup_key(record, dedup_path)
        return f"id={key}"
    except Exception:
        return "record"


def _extract_records(
    items: list[Any], item_path: Optional[str]
) -> list[dict[str, Any]]:
    if not item_path:
        return [it for it in items if isinstance(it, dict)]
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            val = resolve_path(item, item_path)
            if isinstance(val, list):
                out.extend(x for x in val if isinstance(x, dict))
            elif isinstance(val, dict):
                out.append(val)
        except ValueError:
            out.append(item)
    return out


async def _call_list_operation(
    trigger: Trigger,
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> tuple[list[dict[str, Any]], Optional[str]]:
    if not trigger.poll_app or not trigger.poll_resource or not trigger.poll_operation:
        raise ValueError("poll trigger missing app/resource/operation")
    if not trigger.poll_credential:
        raise ValueError("poll trigger missing poll_credential")

    fields: dict[str, Any] = {}
    _, _, op = resolve_operation(
        trigger.poll_app, trigger.poll_resource, trigger.poll_operation
    )
    pagination = op.response.pagination
    if trigger.poll_cursor and pagination and pagination.cursor_param:
        fields[pagination.cursor_param] = trigger.poll_cursor

    with Session(engine) as session:
        result = await integration_node.run(
            {
                "app": trigger.poll_app,
                "resource": trigger.poll_resource,
                "operation": trigger.poll_operation,
                "credential": trigger.poll_credential,
                "fields": fields,
            },
            input_items=[],
            context={},
            session=session,
            workflow_id=trigger.workflow_id,
            transport=transport,
        )

    records: list[dict[str, Any]] = []
    for item in result.items:
        if isinstance(item.json, dict):
            records.append(item.json)

    new_cursor: Optional[str] = None
    if pagination and pagination.cursor_path:
        try:
            cursor_val = resolve_path(result.output, pagination.cursor_path)
            if cursor_val:
                new_cursor = str(cursor_val)
        except ValueError:
            pass
    return records, new_cursor


def _select_new_records(
    records: list[dict[str, Any]],
    dedup_path: str,
    seen: set[str],
    last_seen_key: Optional[str],
) -> list[dict[str, Any]]:
    new: list[dict[str, Any]] = []
    for record in records:
        try:
            key = _dedup_key(record, dedup_path)
        except ValueError:
            continue
        if key in seen:
            continue
        if last_seen_key is not None and not _key_gt(key, last_seen_key):
            continue
        new.append(record)
    return new


def _apply_first_poll(
    records: list[dict[str, Any]],
    mode: str,
    dedup_path: str,
) -> list[dict[str, Any]]:
    if not records:
        return []
    if mode == "fire_all":
        return records
    if mode == "fire_latest":
        best = records[0]
        best_key = _dedup_key(best, dedup_path)
        for rec in records[1:]:
            try:
                key = _dedup_key(rec, dedup_path)
            except ValueError:
                continue
            if _key_gt(key, best_key):
                best = rec
                best_key = key
        return [best]
    return []


def _enqueue_poll_run(
    trigger: Trigger,
    record: dict[str, Any],
    *,
    batched_items: Optional[list[dict[str, Any]]] = None,
) -> None:
    dedup_path = trigger.poll_dedup_path or "id"
    if batched_items is not None:
        context_payload = {"items": batched_items}
        summary = f"{len(batched_items)} records"
    else:
        context_payload = record
        summary = _record_summary(record, dedup_path)

    ctx = {
        "kind": "poll",
        "trigger_id": trigger.id,
        "record_summary": summary,
        "context": context_payload,
    }
    run_svc.enqueue_run_standalone(
        trigger.workflow_id,
        source="poll",
        trigger_id=trigger.id,
        trigger_context=ctx,
    )


async def tick_trigger(
    trigger_id: str,
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
    force: bool = False,
) -> int:
    """Run one poll cycle for ``trigger_id``. Returns number of runs enqueued."""
    with Session(engine) as session:
        trigger = session.get(Trigger, trigger_id)
        if trigger is None or trigger.type != "poll" or not trigger.enabled:
            return 0

        now = _utcnow()
        if not force and trigger.last_polled_at is not None:
            elapsed = (now - _as_utc(trigger.last_polled_at)).total_seconds()
            if elapsed < trigger.min_poll_interval_s:
                return 0

        dedup_path = trigger.poll_dedup_path or "id"
        seen = _load_seen_keys(trigger.seen_keys_json)

    try:
        records, new_cursor = await _call_list_operation(
            trigger, transport=transport
        )
    except Exception:
        logger.exception("poll list operation failed trigger=%s", trigger_id)
        return 0

    to_fire: list[dict[str, Any]]
    if not trigger.first_poll_done:
        to_fire = _apply_first_poll(records, trigger.on_first_poll, dedup_path)
        for rec in records:
            try:
                seen.add(_dedup_key(rec, dedup_path))
            except ValueError:
                pass
    else:
        to_fire = _select_new_records(
            records, dedup_path, seen, trigger.last_seen_key
        )

    enqueued = 0
    if to_fire:
        if trigger.poll_mode == "batched":
            _enqueue_poll_run(trigger, to_fire[0], batched_items=to_fire)
            enqueued = 1
        else:
            for rec in to_fire:
                _enqueue_poll_run(trigger, rec)
                enqueued += 1

    for rec in to_fire:
        try:
            seen.add(_dedup_key(rec, dedup_path))
        except ValueError:
            pass

    max_key = trigger.last_seen_key
    for rec in records:
        try:
            key = _dedup_key(rec, dedup_path)
            seen.add(key)
            if max_key is None or _key_gt(key, max_key):
                max_key = key
        except ValueError:
            pass

    with Session(engine) as session:
        row = session.get(Trigger, trigger_id)
        if row is None:
            return enqueued
        row.last_polled_at = now
        row.first_poll_done = True
        row.seen_keys_json = _dump_seen_keys(seen)
        row.last_seen_key = max_key
        if new_cursor:
            row.poll_cursor = new_cursor
        if enqueued:
            row.last_fired_at = now
        row.updated_at = now
        session.add(row)
        session.commit()

    return enqueued


__all__ = ["tick_trigger"]
