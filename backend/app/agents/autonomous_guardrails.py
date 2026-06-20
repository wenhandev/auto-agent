"""Guardrails for autonomous task mode (enforced outside the LLM)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlparse

from app.services.perception import Observation

NO_PROGRESS_THRESHOLD = 7

ConfirmationHandler = Callable[[str, dict[str, Any]], Awaitable[bool]]


@dataclass
class BudgetClock:
    max_steps: int
    max_seconds: int
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    steps_used: int = 0

    def deadline_exceeded(self) -> bool:
        elapsed = (datetime.now(timezone.utc) - self.started_at).total_seconds()
        return elapsed >= self.max_seconds

    def step_budget_exhausted(self) -> bool:
        return self.steps_used >= self.max_steps

    def record_step(self) -> None:
        self.steps_used += 1


@dataclass
class ProgressTracker:
    threshold: int = NO_PROGRESS_THRESHOLD
    _fingerprints: list[str] = field(default_factory=list)
    _last_action: Optional[str] = None

    @staticmethod
    def _element_map_hash(observation: Observation) -> str:
        parts = tuple(
            (el.role, el.name, el.signature_metadata.get("value", ""))
            for el in observation.elements
        )
        return hashlib.sha256(repr(parts).encode()).hexdigest()[:16]

    def fingerprint(
        self,
        observation: Observation,
        *,
        data_items_count: int,
    ) -> str:
        text_hash = hashlib.sha256(
            observation.page_text_summary.encode("utf-8", errors="ignore")
        ).hexdigest()[:12]
        return json.dumps(
            {
                "url": observation.url,
                "element_hash": self._element_map_hash(observation),
                "data_items": data_items_count,
                "text_hash": text_hash,
            },
            sort_keys=True,
        )

    def record(
        self,
        observation: Observation,
        *,
        action_label: str,
        data_items_count: int,
    ) -> Optional[str]:
        """Return diagnostic if no-progress threshold reached."""
        fp = self.fingerprint(observation, data_items_count=data_items_count)
        if self._fingerprints and self._fingerprints[-1] == fp:
            self._fingerprints.append(fp)
        else:
            self._fingerprints = [fp]
        self._last_action = action_label
        if len(self._fingerprints) >= self.threshold:
            recent = self._fingerprints[-self.threshold :]
            if len(set(recent)) == 1:
                return (
                    f"no progress over {self.threshold} steps: "
                    f"repeated action {action_label!r} with unchanged state "
                    f"(url={observation.url})"
                )
        return None


def host_of(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def check_navigation(url: str, allowed_domains: Optional[list[str]]) -> Optional[str]:
    """Return error message if navigation is blocked, else None."""
    if not allowed_domains:
        return None
    host = host_of(url)
    allowed = {d.lower().removeprefix("www.") for d in allowed_domains}
    if host not in allowed:
        return f"navigation to {host} blocked (not in allowed_domains)"
    return None


_DESTRUCTIVE_KEYWORDS = (
    "checkout",
    "purchase",
    "buy now",
    "pay",
    "payment",
    "delete",
    "remove account",
    "confirm order",
    "place order",
    "submit payment",
)


def is_destructive_action(
    tool_name: str,
    args: dict[str, Any],
    *,
    observation: Optional[Observation] = None,
) -> bool:
    if tool_name == "integration":
        operation = str(args.get("operation", "")).lower()
        if operation in ("create", "update", "delete", "send", "write", "post"):
            return True
    if tool_name in ("click_element", "type_text", "select_option"):
        if observation is None:
            return False
        index = args.get("index")
        if index is None:
            return False
        try:
            idx = int(index)
        except (TypeError, ValueError):
            return False
        if idx < 0 or idx >= len(observation.elements):
            return False
        el = observation.elements[idx]
        label = f"{el.role} {el.name}".lower()
        if any(kw in label for kw in _DESTRUCTIVE_KEYWORDS):
            return True
        if el.role == "button" and any(
            kw in el.name.lower() for kw in ("pay", "buy", "delete", "checkout")
        ):
            return True
    return False


async def default_confirmation_handler(
    description: str, action: dict[str, Any]
) -> bool:
    """Stub human-in-the-loop gate: auto-approve (production would pause)."""
    return True


class ConfirmationGate:
    def __init__(
        self,
        enabled: bool,
        handler: Optional[ConfirmationHandler] = None,
    ) -> None:
        self.enabled = enabled
        self.handler = handler or default_confirmation_handler
        self.last_pause_reason: Optional[str] = None

    async def check(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        observation: Optional[Observation] = None,
    ) -> tuple[bool, Optional[str]]:
        """Return (allowed, pause_reason). pause_reason set when waiting."""
        if not self.enabled:
            return True, None
        if not is_destructive_action(tool_name, args, observation=observation):
            return True, None
        desc = f"{tool_name}({json.dumps(args, default=str)[:120]})"
        approved = await self.handler(desc, {"tool": tool_name, "args": args})
        if approved:
            return True, None
        self.last_pause_reason = f"confirmation rejected for {desc}"
        return False, self.last_pause_reason


__all__ = [
    "NO_PROGRESS_THRESHOLD",
    "BudgetClock",
    "ProgressTracker",
    "ConfirmationGate",
    "ConfirmationHandler",
    "check_navigation",
    "host_of",
    "is_destructive_action",
    "default_confirmation_handler",
]
