"""Agent loop metrics accumulator for autonomous and hybrid primitive runs."""

from __future__ import annotations

import contextvars
import json
from dataclasses import dataclass, field
from typing import Any, Optional

from app.db.models import Run


_metrics_ctx: contextvars.ContextVar[Optional["AgentLoopMetrics"]] = contextvars.ContextVar(
    "agent_loop_metrics",
    default=None,
)


@dataclass
class AgentLoopMetrics:
    rounds: int = 0
    tool_successes: int = 0
    tool_failures: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    computer_use_fallbacks: int = 0
    no_effect_count: int = 0
    stop_reason: Optional[str] = None

    def record_round(self) -> None:
        self.rounds += 1

    def record_tool_result(self, *, success: bool) -> None:
        if success:
            self.tool_successes += 1
        else:
            self.tool_failures += 1

    def record_cache(self, *, hit: bool) -> None:
        if hit:
            self.cache_hits += 1
        else:
            self.cache_misses += 1

    def record_computer_use_fallback(self) -> None:
        self.computer_use_fallbacks += 1

    def record_no_effect(self) -> None:
        self.no_effect_count += 1

    def finalize(self, stop_reason: str, run: Optional[Run] = None) -> dict[str, Any]:
        self.stop_reason = stop_reason
        summary: dict[str, Any] = {
            "rounds": self.rounds,
            "tool_successes": self.tool_successes,
            "tool_failures": self.tool_failures,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "computer_use_fallbacks": self.computer_use_fallbacks,
            "no_effect_count": self.no_effect_count,
            "stop_reason": stop_reason,
        }
        if run is not None:
            summary["usage"] = {
                "total_input_tokens": int(getattr(run, "total_input_tokens", 0) or 0),
                "total_output_tokens": int(getattr(run, "total_output_tokens", 0) or 0),
                "total_llm_calls": int(getattr(run, "total_llm_calls", 0) or 0),
                "total_vision_calls": int(getattr(run, "total_vision_calls", 0) or 0),
                "estimated_cost_usd": getattr(run, "estimated_cost_usd", None),
            }
        return summary

    def to_dict(self) -> dict[str, Any]:
        return {
            "rounds": self.rounds,
            "tool_successes": self.tool_successes,
            "tool_failures": self.tool_failures,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "computer_use_fallbacks": self.computer_use_fallbacks,
            "no_effect_count": self.no_effect_count,
            "stop_reason": self.stop_reason,
        }


def get_metrics() -> Optional[AgentLoopMetrics]:
    return _metrics_ctx.get()


def set_metrics(metrics: Optional[AgentLoopMetrics]) -> contextvars.Token:
    return _metrics_ctx.set(metrics)


def reset_metrics(token: contextvars.Token) -> None:
    _metrics_ctx.reset(token)


def observe_event(payload: dict[str, Any]) -> None:
    metrics = get_metrics()
    if metrics is None:
        return
    event = payload.get("event")
    if event == "cache_hit":
        metrics.record_cache(hit=True)
    elif event == "cache_miss":
        metrics.record_cache(hit=False)
    elif event == "computer_use_action":
        metrics.record_computer_use_fallback()
    elif event == "vision_step":
        result = payload.get("result")
        success = not (isinstance(result, dict) and result.get("error"))
        metrics.record_tool_result(success=success)
        effect = payload.get("action_effect")
        if isinstance(effect, dict) and "no visible effect" in str(effect.get("summary", "")):
            metrics.record_no_effect()
    elif event == "primitive_act":
        source = payload.get("source")
        if source == "cache":
            metrics.record_cache(hit=True)
        elif source in ("resolver", "perception"):
            metrics.record_cache(hit=False)
        elif source == "computer_use":
            metrics.record_computer_use_fallback()
        result = payload.get("result")
        success = not (isinstance(result, dict) and result.get("error"))
        metrics.record_tool_result(success=success)


def persist_metrics(run_id: str, summary: dict[str, Any]) -> None:
    from sqlmodel import Session

    from app.db.session import engine

    with Session(engine) as session:
        row = session.get(Run, run_id)
        if row is None:
            return
        row.agent_loop_metrics_json = json.dumps(summary, ensure_ascii=False, default=str)
        session.add(row)
        session.commit()


def parse_metrics_json(raw: Optional[str]) -> Optional[dict[str, Any]]:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


__all__ = [
    "AgentLoopMetrics",
    "get_metrics",
    "observe_event",
    "parse_metrics_json",
    "persist_metrics",
    "reset_metrics",
    "set_metrics",
]
