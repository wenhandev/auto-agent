"""Per-run LLM token/cost aggregation and model price estimation."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlmodel import Session, select

from app.db.models import Run
from app.db.session import engine
from app.services import artifact_context


logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PRICES_PATH = _BACKEND_ROOT / "data" / "model_prices.json"
_PRICES_MARKER = _BACKEND_ROOT / ".model_prices_seeded"

DEFAULT_MODEL_PRICES: dict[str, dict[str, float]] = {
    "gpt-4o": {"input_per_1k": 0.0025, "output_per_1k": 0.01},
    "gpt-4o-mini": {"input_per_1k": 0.00015, "output_per_1k": 0.0006},
    "gemini-2.0-flash": {"input_per_1k": 0.0001, "output_per_1k": 0.0004},
    "gemini-2.5-flash": {"input_per_1k": 0.00015, "output_per_1k": 0.0006},
}

UNKNOWN_PRICE_NOTE = "未知价格"


@dataclass
class UsageDelta:
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0
    vision_calls: int = 0
    model: Optional[str] = None
    call_id: Optional[str] = None
    source: str = "hint"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _empty_usage_summary() -> dict[str, Any]:
    return {"models": {}, "processed_call_ids": []}


def _load_summary_json(raw: Optional[str]) -> dict[str, Any]:
    if not raw:
        return _empty_usage_summary()
    try:
        parsed = json.loads(raw)
    except Exception:
        return _empty_usage_summary()
    if not isinstance(parsed, dict):
        return _empty_usage_summary()
    parsed.setdefault("models", {})
    parsed.setdefault("processed_call_ids", [])
    return parsed


def _load_node_costs_json(raw: Optional[str]) -> dict[str, dict[str, Any]]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _dump_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def ensure_model_prices_seeded() -> None:
    """Seed default model prices on first boot."""
    if _PRICES_MARKER.exists() and _PRICES_PATH.is_file():
        return
    _PRICES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _PRICES_PATH.is_file():
        _PRICES_PATH.write_text(
            json.dumps(DEFAULT_MODEL_PRICES, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _PRICES_MARKER.write_text("ok\n", encoding="utf-8")
    logger.info("seeded default model_prices at %s", _PRICES_PATH)


def get_model_prices() -> dict[str, dict[str, float]]:
    ensure_model_prices_seeded()
    try:
        raw = json.loads(_PRICES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULT_MODEL_PRICES)
    if not isinstance(raw, dict):
        return dict(DEFAULT_MODEL_PRICES)
    out: dict[str, dict[str, float]] = {}
    for model, rates in raw.items():
        if not isinstance(rates, dict):
            continue
        try:
            out[str(model)] = {
                "input_per_1k": float(rates["input_per_1k"]),
                "output_per_1k": float(rates["output_per_1k"]),
            }
        except (KeyError, TypeError, ValueError):
            continue
    return out or dict(DEFAULT_MODEL_PRICES)


def save_model_prices(prices: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    ensure_model_prices_seeded()
    normalized: dict[str, dict[str, float]] = {}
    for model, rates in prices.items():
        normalized[str(model)] = {
            "input_per_1k": float(rates["input_per_1k"]),
            "output_per_1k": float(rates["output_per_1k"]),
        }
    _PRICES_PATH.write_text(
        json.dumps(normalized, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return normalized


def usage_from_genai_response(response: Any) -> dict[str, Optional[int]]:
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return {"input_tokens": None, "output_tokens": None}
    input_tokens = getattr(meta, "prompt_token_count", None)
    output_tokens = getattr(meta, "candidates_token_count", None)
    if output_tokens is None:
        output_tokens = getattr(meta, "completion_token_count", None)
    return {
        "input_tokens": int(input_tokens) if input_tokens is not None else None,
        "output_tokens": int(output_tokens) if output_tokens is not None else None,
    }


def _coerce_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _estimate_cost(
    usage_summary: dict[str, Any],
    prices: dict[str, dict[str, float]],
) -> tuple[Optional[float], Optional[str]]:
    total = 0.0
    unknown_models: list[str] = []
    models = usage_summary.get("models") or {}
    if not models:
        return None, None
    for model, stats in models.items():
        if not isinstance(stats, dict):
            continue
        rates = prices.get(str(model))
        if rates is None:
            unknown_models.append(str(model))
            continue
        inp = _coerce_int(stats.get("input_tokens"))
        out = _coerce_int(stats.get("output_tokens"))
        total += (inp / 1000.0) * rates["input_per_1k"]
        total += (out / 1000.0) * rates["output_per_1k"]
    if unknown_models:
        return None, UNKNOWN_PRICE_NOTE
    return round(total, 6), None


def _apply_delta_to_node(
    node_costs: dict[str, dict[str, Any]],
    node_id: Optional[str],
    delta: UsageDelta,
) -> None:
    if not node_id:
        return
    entry = node_costs.setdefault(
        node_id,
        {
            "input_tokens": 0,
            "output_tokens": 0,
            "llm_calls": 0,
            "vision_calls": 0,
            "models": {},
        },
    )
    entry["input_tokens"] = _coerce_int(entry.get("input_tokens")) + delta.input_tokens
    entry["output_tokens"] = _coerce_int(entry.get("output_tokens")) + delta.output_tokens
    entry["llm_calls"] = _coerce_int(entry.get("llm_calls")) + delta.llm_calls
    entry["vision_calls"] = _coerce_int(entry.get("vision_calls")) + delta.vision_calls
    if delta.model:
        models = entry.setdefault("models", {})
        model_stats = models.setdefault(
            delta.model,
            {"input_tokens": 0, "output_tokens": 0, "llm_calls": 0},
        )
        model_stats["input_tokens"] = (
            _coerce_int(model_stats.get("input_tokens")) + delta.input_tokens
        )
        model_stats["output_tokens"] = (
            _coerce_int(model_stats.get("output_tokens")) + delta.output_tokens
        )
        model_stats["llm_calls"] = (
            _coerce_int(model_stats.get("llm_calls")) + delta.llm_calls
        )


def _apply_delta_to_run(row: Run, delta: UsageDelta, *, node_id: Optional[str]) -> None:
    if (
        delta.input_tokens == 0
        and delta.output_tokens == 0
        and delta.llm_calls == 0
        and delta.vision_calls == 0
    ):
        return

    summary = _load_summary_json(getattr(row, "usage_summary_json", None))
    processed: set[str] = set(summary.get("processed_call_ids") or [])
    if delta.call_id:
        if delta.call_id in processed:
            return
        processed.add(delta.call_id)
        summary["processed_call_ids"] = sorted(processed)

    row.total_input_tokens = _coerce_int(getattr(row, "total_input_tokens", 0)) + delta.input_tokens
    row.total_output_tokens = _coerce_int(getattr(row, "total_output_tokens", 0)) + delta.output_tokens
    row.total_llm_calls = _coerce_int(getattr(row, "total_llm_calls", 0)) + delta.llm_calls
    row.total_vision_calls = _coerce_int(getattr(row, "total_vision_calls", 0)) + delta.vision_calls

    if delta.model:
        models = summary.setdefault("models", {})
        model_stats = models.setdefault(
            delta.model,
            {"input_tokens": 0, "output_tokens": 0, "llm_calls": 0},
        )
        model_stats["input_tokens"] = (
            _coerce_int(model_stats.get("input_tokens")) + delta.input_tokens
        )
        model_stats["output_tokens"] = (
            _coerce_int(model_stats.get("output_tokens")) + delta.output_tokens
        )
        model_stats["llm_calls"] = (
            _coerce_int(model_stats.get("llm_calls")) + delta.llm_calls
        )

    node_costs = _load_node_costs_json(getattr(row, "node_cost_json", None))
    _apply_delta_to_node(node_costs, node_id, delta)
    row.node_cost_json = _dump_json(node_costs)
    row.usage_summary_json = _dump_json(summary)

    prices = get_model_prices()
    estimated, note = _estimate_cost(summary, prices)
    row.estimated_cost_usd = estimated
    row.cost_note = note


def _delta_from_cost_hint(
    cost_hint: dict[str, Any],
    *,
    model: Optional[str] = None,
    call_id: Optional[str] = None,
) -> UsageDelta:
    vision_calls = _coerce_int(cost_hint.get("vision_calls"))
    llm_calls = 1 if vision_calls or cost_hint.get("input_tokens") is not None else 0
    return UsageDelta(
        input_tokens=_coerce_int(cost_hint.get("input_tokens")),
        output_tokens=_coerce_int(cost_hint.get("output_tokens")),
        llm_calls=llm_calls,
        vision_calls=vision_calls,
        model=model,
        call_id=call_id,
        source="hint",
    )


def _delta_from_llm_trace(trace: dict[str, Any]) -> UsageDelta:
    return UsageDelta(
        input_tokens=_coerce_int(trace.get("input_tokens") or trace.get("prompt_tokens")),
        output_tokens=_coerce_int(
            trace.get("output_tokens") or trace.get("completion_tokens")
        ),
        llm_calls=1,
        vision_calls=_coerce_int(trace.get("vision_calls")),
        model=str(trace["model"]) if trace.get("model") else None,
        call_id=str(trace["call_id"]) if trace.get("call_id") else None,
        source="trace",
    )


def record_llm_usage(
    run_id: str,
    *,
    model: str,
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    node_id: Optional[str] = None,
    vision_calls: int = 0,
    call_id: Optional[str] = None,
    session: Optional[Session] = None,
) -> None:
    """Record token usage from a direct LLM call site."""
    delta = UsageDelta(
        input_tokens=_coerce_int(input_tokens),
        output_tokens=_coerce_int(output_tokens),
        llm_calls=1,
        vision_calls=vision_calls,
        model=model,
        call_id=call_id,
        source="direct",
    )
    _mutate_run(run_id, delta, node_id=node_id or artifact_context.get_node_id(), session=session)


def on_run_event(run_id: str, payload: dict[str, Any], *, session: Optional[Session] = None) -> None:
    """Accumulate cost signals from a persisted run event payload."""
    node_id = payload.get("node_id")
    trace = payload.get("llm_trace")
    if isinstance(trace, dict):
        _mutate_run(run_id, _delta_from_llm_trace(trace), node_id=node_id, session=session)

    cost_hint = payload.get("cost_hint")
    if not isinstance(cost_hint, dict):
        return

    call_id = None
    if isinstance(trace, dict) and trace.get("call_id"):
        call_id = str(trace["call_id"])
    elif cost_hint.get("call_id"):
        call_id = str(cost_hint["call_id"])

    if isinstance(trace, dict) and trace.get("call_id"):
        return

    with Session(engine) as check_session:
        row = check_session.get(Run, run_id)
        if row is None:
            return
        summary = _load_summary_json(getattr(row, "usage_summary_json", None))
        processed = set(summary.get("processed_call_ids") or [])
        if call_id and call_id in processed:
            return

    model = str(cost_hint["model"]) if cost_hint.get("model") else None
    delta = _delta_from_cost_hint(cost_hint, model=model, call_id=call_id)
    _mutate_run(run_id, delta, node_id=node_id, session=session)


def _mutate_run(
    run_id: str,
    delta: UsageDelta,
    *,
    node_id: Optional[str],
    session: Optional[Session] = None,
) -> None:
    own_session = session is None
    sess = session or Session(engine)
    try:
        row = sess.get(Run, run_id)
        if row is None:
            return
        _apply_delta_to_run(row, delta, node_id=node_id)
        sess.add(row)
        if own_session:
            sess.commit()
    finally:
        if own_session:
            sess.close()


def rollup_child_to_parent(
    *,
    parent_run_id: str,
    child_run_id: str,
    parent_node_id: Optional[str] = None,
    session: Optional[Session] = None,
) -> None:
    """Roll a completed child run's totals into its parent."""
    own_session = session is None
    sess = session or Session(engine)
    try:
        child = sess.get(Run, child_run_id)
        parent = sess.get(Run, parent_run_id)
        if child is None or parent is None:
            return

        delta = UsageDelta(
            input_tokens=_coerce_int(getattr(child, "total_input_tokens", 0)),
            output_tokens=_coerce_int(getattr(child, "total_output_tokens", 0)),
            llm_calls=_coerce_int(getattr(child, "total_llm_calls", 0)),
            vision_calls=_coerce_int(getattr(child, "total_vision_calls", 0)),
            source="rollup",
        )
        if (
            delta.input_tokens == 0
            and delta.output_tokens == 0
            and delta.llm_calls == 0
            and delta.vision_calls == 0
        ):
            return

        child_summary = _load_summary_json(getattr(child, "usage_summary_json", None))
        parent_summary = _load_summary_json(getattr(parent, "usage_summary_json", None))
        for model, stats in (child_summary.get("models") or {}).items():
            if not isinstance(stats, dict):
                continue
            target = parent_summary.setdefault("models", {}).setdefault(
                model,
                {"input_tokens": 0, "output_tokens": 0, "llm_calls": 0},
            )
            target["input_tokens"] = _coerce_int(target.get("input_tokens")) + _coerce_int(
                stats.get("input_tokens")
            )
            target["output_tokens"] = _coerce_int(target.get("output_tokens")) + _coerce_int(
                stats.get("output_tokens")
            )
            target["llm_calls"] = _coerce_int(target.get("llm_calls")) + _coerce_int(
                stats.get("llm_calls")
            )
        processed = set(parent_summary.get("processed_call_ids") or [])
        processed.update(child_summary.get("processed_call_ids") or [])
        parent_summary["processed_call_ids"] = sorted(processed)
        parent.usage_summary_json = _dump_json(parent_summary)

        parent.total_input_tokens = _coerce_int(getattr(parent, "total_input_tokens", 0)) + delta.input_tokens
        parent.total_output_tokens = _coerce_int(getattr(parent, "total_output_tokens", 0)) + delta.output_tokens
        parent.total_llm_calls = _coerce_int(getattr(parent, "total_llm_calls", 0)) + delta.llm_calls
        parent.total_vision_calls = _coerce_int(getattr(parent, "total_vision_calls", 0)) + delta.vision_calls

        if parent_node_id:
            node_costs = _load_node_costs_json(getattr(parent, "node_cost_json", None))
            child_nodes = _load_node_costs_json(getattr(child, "node_cost_json", None))
            entry = node_costs.setdefault(
                parent_node_id,
                {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "llm_calls": 0,
                    "vision_calls": 0,
                    "models": {},
                    "child_run_id": child_run_id,
                    "child_nodes": child_nodes,
                },
            )
            entry["input_tokens"] = _coerce_int(entry.get("input_tokens")) + delta.input_tokens
            entry["output_tokens"] = _coerce_int(entry.get("output_tokens")) + delta.output_tokens
            entry["llm_calls"] = _coerce_int(entry.get("llm_calls")) + delta.llm_calls
            entry["vision_calls"] = _coerce_int(entry.get("vision_calls")) + delta.vision_calls
            entry["child_run_id"] = child_run_id
            entry["child_nodes"] = child_nodes
            parent.node_cost_json = _dump_json(node_costs)

        if getattr(child, "cost_note", None) == UNKNOWN_PRICE_NOTE:
            parent.estimated_cost_usd = None
            parent.cost_note = UNKNOWN_PRICE_NOTE
        else:
            prices = get_model_prices()
            estimated, note = _estimate_cost(parent_summary, prices)
            parent.estimated_cost_usd = estimated
            parent.cost_note = note

        sess.add(parent)
        if own_session:
            sess.commit()
    finally:
        if own_session:
            sess.close()


def parse_usage_summary(raw: Optional[str]) -> Optional[dict[str, Any]]:
    summary = _load_summary_json(raw)
    if not summary.get("models"):
        return None
    return summary


def parse_node_costs(raw: Optional[str]) -> list[dict[str, Any]]:
    data = _load_node_costs_json(raw)
    rows: list[dict[str, Any]] = []
    for node_id, stats in data.items():
        if not isinstance(stats, dict):
            continue
        rows.append({"node_id": node_id, **stats})
    return rows


def window_cost_summary(
    *,
    from_ts: datetime,
    to_ts: datetime,
    session: Optional[Session] = None,
) -> dict[str, Any]:
    own_session = session is None
    sess = session or Session(engine)
    try:
        rows = list(
            sess.exec(
                select(Run).where(
                    Run.queued_at >= from_ts,
                    Run.queued_at <= to_ts,
                )
            ).all()
        )
        total_input = 0
        total_output = 0
        total_llm = 0
        total_vision = 0
        cost_sum = 0.0
        known_cost_runs = 0
        unknown_cost_runs = 0
        for row in rows:
            total_input += _coerce_int(getattr(row, "total_input_tokens", 0))
            total_output += _coerce_int(getattr(row, "total_output_tokens", 0))
            total_llm += _coerce_int(getattr(row, "total_llm_calls", 0))
            total_vision += _coerce_int(getattr(row, "total_vision_calls", 0))
            est = getattr(row, "estimated_cost_usd", None)
            if est is None:
                if (
                    _coerce_int(getattr(row, "total_input_tokens", 0))
                    or _coerce_int(getattr(row, "total_output_tokens", 0))
                ):
                    unknown_cost_runs += 1
            else:
                cost_sum += float(est)
                known_cost_runs += 1
        return {
            "from": from_ts,
            "to": to_ts,
            "total_runs": len(rows),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_llm_calls": total_llm,
            "total_vision_calls": total_vision,
            "estimated_cost_usd": round(cost_sum, 6) if known_cost_runs else None,
            "runs_with_known_cost": known_cost_runs,
            "runs_with_unknown_cost": unknown_cost_runs,
        }
    finally:
        if own_session:
            sess.close()


def reset_prices_for_tests() -> None:
    """Restore default prices file (tests)."""
    if _PRICES_PATH.is_file():
        _PRICES_PATH.unlink()
    if _PRICES_MARKER.is_file():
        _PRICES_MARKER.unlink()


__all__ = [
    "DEFAULT_MODEL_PRICES",
    "UNKNOWN_PRICE_NOTE",
    "ensure_model_prices_seeded",
    "get_model_prices",
    "on_run_event",
    "parse_node_costs",
    "parse_usage_summary",
    "record_llm_usage",
    "reset_prices_for_tests",
    "rollup_child_to_parent",
    "save_model_prices",
    "usage_from_genai_response",
    "window_cost_summary",
]
