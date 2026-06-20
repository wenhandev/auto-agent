from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.agents.synthesizer import synthesize_from_recording
from app.db.models import Recording
from app.db.session import get_session
from app.schemas_api import (
    RecordingCreate,
    RecordingEventIn,
    RecordingEventsIn,
    RecordingGenerateOut,
    RecordingOut,
)
from app.services.recording import (
    get_active_events,
    ingest_events,
    load_events,
    start_recording,
    stop_recording,
)


router = APIRouter(prefix="/api/recordings", tags=["recordings"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_out(recording: Recording) -> RecordingOut:
    events = load_events(recording)
    generated: Optional[dict[str, Any]] = None
    if recording.generated_workflow_json:
        try:
            generated = json.loads(recording.generated_workflow_json)
        except Exception:
            generated = None
    return RecordingOut(
        id=recording.id,
        status=recording.status,  # type: ignore[arg-type]
        name=recording.name,
        browser_profile_id=recording.browser_profile_id,
        start_url=recording.start_url,
        event_count=len(events),
        events=events,
        generated_workflow_id=recording.generated_workflow_id,
        generated_workflow=generated,
        created_at=recording.created_at,
        started_at=recording.started_at,
        stopped_at=recording.stopped_at,
    )


@router.get("", response_model=list[RecordingOut])
def list_recordings(session: Session = Depends(get_session)) -> list[RecordingOut]:
    rows = session.exec(
        select(Recording).order_by(Recording.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    return [_to_out(row) for row in rows]


@router.post("", response_model=RecordingOut)
async def create_recording(
    body: RecordingCreate, session: Session = Depends(get_session)
) -> RecordingOut:
    try:
        recording = await start_recording(
            session,
            browser_profile_id=body.browser_profile_id,
            start_url=body.start_url,
            name=body.name,
            acquire_browser=body.acquire_browser,
        )
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    return _to_out(recording)


@router.get("/{recording_id}", response_model=RecordingOut)
def get_recording(
    recording_id: str, session: Session = Depends(get_session)
) -> RecordingOut:
    recording = session.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(404, detail="recording not found")
    return _to_out(recording)


@router.post("/{recording_id}/stop", response_model=RecordingOut)
async def stop_recording_route(
    recording_id: str, session: Session = Depends(get_session)
) -> RecordingOut:
    try:
        recording = await stop_recording(session, recording_id)
    except ValueError as exc:
        msg = str(exc)
        code = 404 if "not found" in msg else 409
        raise HTTPException(code, detail=msg) from exc
    return _to_out(recording)


@router.post("/{recording_id}/events")
def append_recording_events(
    recording_id: str,
    body: RecordingEventsIn,
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    recording = session.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(404, detail="recording not found")
    if recording.status != "active":
        raise HTTPException(409, detail="recording is not active")
    try:
        return ingest_events(
            session,
            recording_id,
            [e.model_dump(exclude_none=True) for e in body.events],
        )
    except ValueError as exc:
        raise HTTPException(409, detail=str(exc)) from exc


@router.get("/{recording_id}/events/live")
def get_live_recording_events(recording_id: str) -> list[dict[str, Any]]:
    return get_active_events(recording_id)


@router.post("/{recording_id}/generate", response_model=RecordingGenerateOut)
def generate_workflow_from_recording(
    recording_id: str,
    session: Session = Depends(get_session),
) -> RecordingGenerateOut:
    recording = session.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(404, detail="recording not found")
    if recording.status == "active":
        raise HTTPException(409, detail="stop the recording before generating")
    if recording.status == "synthesized" and recording.generated_workflow_id:
        from app.services import workflows as workflow_svc

        chat = workflow_svc.ensure_chat_session(recording.generated_workflow_id, session)
        graph: dict[str, Any] = {}
        if recording.generated_workflow_json:
            try:
                graph = json.loads(recording.generated_workflow_json)
            except Exception:
                graph = {}
        return RecordingGenerateOut(
            recording_id=recording.id,
            workflow_id=recording.generated_workflow_id,
            chat_session_id=chat.id,
            workflow=graph,
        )
    if recording.status != "stopped":
        raise HTTPException(409, detail="recording must be stopped before generating")

    try:
        workflow_id, graph, chat_id = synthesize_from_recording(recording, session)
    except Exception as exc:
        raise HTTPException(422, detail=f"synthesis failed: {exc}") from exc

    return RecordingGenerateOut(
        recording_id=recording.id,
        workflow_id=workflow_id,
        chat_session_id=chat_id,
        workflow=graph,
    )


@router.post("/{recording_id}/synthesize", response_model=RecordingGenerateOut)
def synthesize_recording_alias(
    recording_id: str,
    session: Session = Depends(get_session),
) -> RecordingGenerateOut:
    return generate_workflow_from_recording(recording_id, session)


__all__ = ["router"]
