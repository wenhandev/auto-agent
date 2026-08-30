"""Atomize, classify, and distill browser action traces into route skill proposals."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from sqlmodel import Session, select

from app.agents.synthesizer import trace_to_graph, validate_workflow_graph
from app.db.models import Recording, RouteSkillProposal
from app.services.recording import load_events
from app.services.selector_cache import normalize_url

_NOISE_TYPES = frozenset({"scroll", "wait"})
_MERGE_SEPARATOR = "\n\n---\n\n"


@dataclass(frozen=True)
class TraceSegment:
    domain: str
    url_pattern: str
    capability: str
    events: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    start_url: str = ""


@dataclass(frozen=True)
class DistillResult:
    segments: list[TraceSegment]
    workflow_graph: dict[str, Any]
    proposals: list[RouteSkillProposal]
    mode: str


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:64] or "interaction"


def _domain_from_url(url: str) -> str:
    if not url:
        return "unknown"
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.netloc or parsed.path.split("/")[0]
    return host.lower().lstrip("www.") or "unknown"


def _event_url(event: dict[str, Any]) -> str:
    for key in ("url", "page_url"):
        raw = event.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


def _filtered_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in events if event.get("type") not in _NOISE_TYPES]


def atomize_events(events: list[dict[str, Any]]) -> list[TraceSegment]:
    """Split a trace into URL-scoped segments."""
    cleaned = _filtered_events(events)
    if not cleaned:
        return []

    segments: list[TraceSegment] = []
    current_events: list[dict[str, Any]] = []
    current_pattern = ""
    current_url = ""

    def flush() -> None:
        nonlocal current_events, current_pattern, current_url
        if not current_events:
            return
        capability = classify_capability(current_events)
        segments.append(
            TraceSegment(
                domain=_domain_from_url(current_url or current_pattern),
                url_pattern=current_pattern or "unknown",
                capability=capability,
                events=tuple(current_events),
                start_url=current_url or current_pattern,
            )
        )
        current_events = []

    for event in cleaned:
        event_url = _event_url(event)
        pattern = normalize_url(event_url) if event_url else current_pattern
        if current_events and pattern and current_pattern and pattern != current_pattern:
            flush()
        if event_url:
            current_url = event_url
        if pattern:
            current_pattern = pattern
        current_events.append(event)

    flush()
    return segments


def classify_capability(events: list[dict[str, Any]]) -> str:
    """Infer a capability slug from segment event shapes."""
    if any(event.get("sensitive") for event in events):
        return "login-with-credentials"
    types = [str(event.get("type") or "") for event in events]
    if "fill" in types and "click" in types:
        return "search-and-select"
    if any(event.get("type") == "select" for event in events):
        return "form-submit"
    if types and all(t == "navigate" for t in types):
        return "navigation"
    if any(event.get("type") == "fill" for event in events):
        return "form-fill"
    return "site-interaction"


def _step_line(index: int, event: dict[str, Any]) -> str:
    event_type = str(event.get("type") or "step")
    if event.get("sensitive"):
        return f"{index}. Enter credentials in the login form (values not recorded)."
    if event_type == "navigate" and event.get("url"):
        return f"{index}. Navigate to {event['url']}."
    label = (
        event.get("description")
        or event.get("name")
        or event.get("selector")
        or event_type
    )
    if event_type == "fill":
        return f"{index}. Type into {label}."
    if event_type == "click":
        return f"{index}. Click {label}."
    if event_type == "select":
        return f"{index}. Select option in {label}."
    return f"{index}. Perform {label}."


def distill_segment_prompt(segment: TraceSegment) -> str:
    """Convert a segment into route-skill-ready operator instructions."""
    lines = [
        f"# {segment.capability} on {segment.domain}",
        "",
        f"URL pattern: {segment.url_pattern}",
        "",
        "Steps:",
    ]
    for idx, event in enumerate(segment.events, start=1):
        lines.append(_step_line(idx, event))
    lines.append("")
    lines.append(
        "Use vision tools when selectors are unavailable; never log or repeat secrets."
    )
    return "\n".join(lines)


def merge_route_prompts(existing: str, incoming: str) -> str:
    existing = existing.strip()
    incoming = incoming.strip()
    if not existing:
        return incoming
    if not incoming:
        return existing
    if incoming in existing:
        return existing
    return f"{existing}{_MERGE_SEPARATOR}{incoming}"


def _supersede_pending_proposals(
    session: Session,
    *,
    source_type: str,
    source_id: str,
) -> None:
    rows = session.exec(
        select(RouteSkillProposal).where(
            RouteSkillProposal.source_type == source_type,
            RouteSkillProposal.source_id == source_id,
            RouteSkillProposal.status == "pending",
        )
    ).all()
    now = _utcnow()
    for row in rows:
        row.status = "superseded"
        row.updated_at = now
        session.add(row)


def persist_proposals(
    session: Session,
    *,
    source_type: str,
    source_id: str,
    segments: list[TraceSegment],
    org_id: Optional[str] = None,
) -> list[RouteSkillProposal]:
    _supersede_pending_proposals(
        session, source_type=source_type, source_id=source_id
    )
    now = _utcnow()
    proposals: list[RouteSkillProposal] = []
    for segment in segments:
        prompt = distill_segment_prompt(segment)
        row = RouteSkillProposal(
            source_type=source_type,
            source_id=source_id,
            org_id=org_id,
            domain=segment.domain,
            capability=segment.capability,
            url_pattern=segment.url_pattern,
            prompt=prompt,
            evidence_json=json.dumps(list(segment.events), ensure_ascii=False),
            status="pending",
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        proposals.append(row)
    session.commit()
    for row in proposals:
        session.refresh(row)
    return proposals


def build_workflow_graph(
    events: list[dict[str, Any]],
    *,
    recording_name: Optional[str] = None,
) -> dict[str, Any]:
    graph = trace_to_graph(events, recording_name=recording_name)
    validate_workflow_graph(graph)
    return graph


def events_from_task_run(
    *,
    start_url: Optional[str],
    payloads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert autonomous task run events into recording-like trace events."""
    events: list[dict[str, Any]] = []
    current_url = start_url or ""
    seen_navigate = False

    if start_url:
        events.append({
            "type": "navigate",
            "url": start_url,
            "description": "task start",
        })
        seen_navigate = True

    for payload in payloads:
        if payload.get("event") != "vision_step":
            continue
        action = str(payload.get("action") or "")
        thought = str(payload.get("thought") or action)
        args = payload.get("args")
        if not isinstance(args, dict):
            args = {}
        url = str(payload.get("url") or current_url or "")

        if action == "navigate":
            nav_url = args.get("url") or url
            if isinstance(nav_url, str) and nav_url:
                current_url = nav_url
                events.append({
                    "type": "navigate",
                    "url": nav_url,
                    "description": thought,
                })
                seen_navigate = True
            continue

        if not url and current_url:
            url = current_url

        if action == "click_element":
            events.append({
                "type": "click",
                "url": url,
                "description": thought,
            })
        elif action == "type_text":
            text = args.get("text")
            sensitive = isinstance(text, str) and any(
                token in thought.lower()
                for token in ("password", "otp", "2fa", "secret", "credential")
            )
            events.append({
                "type": "fill",
                "url": url,
                "description": thought,
                "sensitive": sensitive,
            })
        elif action == "select_option":
            events.append({
                "type": "select",
                "url": url,
                "description": thought,
                "value": args.get("value"),
            })
        elif action == "extract":
            events.append({
                "type": "click",
                "url": url,
                "description": f"extract: {thought}",
            })
        elif action and action not in ("wait", "scroll"):
            events.append({
                "type": "click",
                "url": url,
                "description": thought or action,
            })

    if not seen_navigate and not events and start_url:
        events.append({
            "type": "navigate",
            "url": start_url,
            "description": "task start",
        })
    return events


def distill_task_run(
    session: Session,
    run_id: str,
    *,
    org_id: Optional[str] = None,
) -> DistillResult:
    from app.db.models import Run
    from app.services.runs import fetch_prior_events

    run = session.get(Run, run_id)
    if run is None or run.mode != "autonomous":
        raise ValueError("autonomous task run not found")
    if run.status != "completed":
        raise ValueError("task run must be completed before distilling route skills")

    result_payload: dict[str, Any] = {}
    if run.result_json:
        try:
            parsed = json.loads(run.result_json)
            if isinstance(parsed, dict):
                result_payload = parsed
        except Exception:
            result_payload = {}
    if not result_payload.get("success"):
        raise ValueError("task run must succeed before distilling route skills")

    trace_events = events_from_task_run(
        start_url=run.start_url,
        payloads=fetch_prior_events(run_id),
    )
    if not trace_events:
        raise ValueError("no distillable browser steps in task run")

    segments = atomize_events(trace_events)
    if not segments:
        raise ValueError("no URL segments found in task trajectory")

    graph = build_workflow_graph(trace_events, recording_name=run.objective)
    proposals = persist_proposals(
        session,
        source_type="task_run",
        source_id=run_id,
        segments=segments,
        org_id=org_id or run.org_id,
    )
    return DistillResult(
        segments=segments,
        workflow_graph=graph,
        proposals=proposals,
        mode="rule",
    )


def distill_recording(
    recording: Recording,
    session: Session,
) -> DistillResult:
    events = load_events(recording)
    segments = atomize_events(events)
    graph = build_workflow_graph(events, recording_name=recording.name)
    proposals = persist_proposals(
        session,
        source_type="recording",
        source_id=recording.id,
        segments=segments,
        org_id=None,
    )
    return DistillResult(
        segments=segments,
        workflow_graph=graph,
        proposals=proposals,
        mode="rule",
    )


async def distill_recording_async(
    recording: Recording,
    session: Session,
    *,
    use_llm: bool = False,
) -> DistillResult:
    events = load_events(recording)
    segments = atomize_events(events)
    mode = "rule"
    if use_llm:
        from app.agents.distiller import distill_workflow_graph

        graph, mode = await distill_workflow_graph(
            events,
            recording_name=recording.name,
        )
    else:
        graph = build_workflow_graph(events, recording_name=recording.name)

    proposals = persist_proposals(
        session,
        source_type="recording",
        source_id=recording.id,
        segments=segments,
        org_id=None,
    )
    return DistillResult(
        segments=segments,
        workflow_graph=graph,
        proposals=proposals,
        mode=mode,
    )


def list_proposals_for_recording(
    session: Session,
    recording_id: str,
) -> list[RouteSkillProposal]:
    rows = session.exec(
        select(RouteSkillProposal)
        .where(
            RouteSkillProposal.source_type == "recording",
            RouteSkillProposal.source_id == recording_id,
        )
        .order_by(RouteSkillProposal.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    active = [row for row in rows if row.status in ("pending", "adopted", "dismissed")]
    return active


__all__ = [
    "TraceSegment",
    "DistillResult",
    "atomize_events",
    "classify_capability",
    "distill_segment_prompt",
    "merge_route_prompts",
    "persist_proposals",
    "build_workflow_graph",
    "distill_recording",
    "distill_recording_async",
    "distill_task_run",
    "events_from_task_run",
    "list_proposals_for_recording",
]
