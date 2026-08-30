from __future__ import annotations

import json
from datetime import datetime
from typing import assert_never

from sqlmodel import Session, select

from app.conversation.model import (
    Asked,
    ControlChanged,
    ConversationEvent,
    Done,
    Failed,
    HandedOff,
    NeedsConfirmation,
    Rejected,
    StageBound,
    StageRef,
    TurnEnded,
    TurnOutcome,
    TurnStarted,
    UserSaid,
)
from app.db.models import Conversation, ConversationEventRow


def get_conversation(session: Session, conversation_id: str) -> Conversation | None:
    return session.get(Conversation, conversation_id)


def find_open(session: Session, owner_id: str) -> Conversation | None:
    stmt = (
        select(Conversation)
        .where(Conversation.owner_id == owner_id)
        .where(Conversation.closed_at == None)  # noqa: E711
        .order_by(Conversation.created_at.desc())
    )
    return session.exec(stmt).first()


def create(session: Session, *, owner_id: str, org_id: str | None) -> Conversation:
    row = Conversation(owner_id=owner_id, org_id=org_id, title="")
    session.add(row)
    session.flush()
    return row


def list_events(session: Session, conversation_id: str) -> list[ConversationEvent]:
    stmt = (
        select(ConversationEventRow)
        .where(ConversationEventRow.conversation_id == conversation_id)
        .order_by(ConversationEventRow.seq)
    )
    return [_from_row(row) for row in session.exec(stmt).all()]


def find_by_client_id(
    session: Session, conversation_id: str, client_id: str
) -> ConversationEventRow | None:
    stmt = (
        select(ConversationEventRow)
        .where(ConversationEventRow.conversation_id == conversation_id)
        .where(ConversationEventRow.client_id == client_id)
    )
    return session.exec(stmt).first()


def append(session: Session, conversation_id: str, event: ConversationEvent) -> None:
    kind, payload, client_id = _split(event)
    session.add(
        ConversationEventRow(
            conversation_id=conversation_id,
            seq=event.seq,
            kind=kind,
            payload_json=json.dumps(payload),
            client_id=client_id,
        )
    )


def _split(event: ConversationEvent) -> tuple[str, dict, str | None]:
    match event:
        case UserSaid(at=at, text=text, client_id=client_id):
            return (
                "user_said",
                {"at": at.isoformat(), "text": text, "client_id": client_id},
                client_id,
            )
        case TurnStarted(
            at=at,
            turn_id=turn_id,
            for_message_seq=for_message_seq,
            objective=objective,
        ):
            return (
                "turn_started",
                {
                    "at": at.isoformat(),
                    "turn_id": turn_id,
                    "for_message_seq": for_message_seq,
                    "objective": objective,
                },
                None,
            )
        case TurnEnded(at=at, turn_id=turn_id, outcome=outcome):
            return (
                "turn_ended",
                {
                    "at": at.isoformat(),
                    "turn_id": turn_id,
                    "outcome": _outcome_payload(outcome),
                },
                None,
            )
        case StageBound(at=at, stage=stage, rebound_from=rebound_from):
            return (
                "stage_bound",
                {
                    "at": at.isoformat(),
                    "stage": _stage_payload(stage),
                    "rebound_from": (
                        None if rebound_from is None else _stage_payload(rebound_from)
                    ),
                },
                None,
            )
        case ControlChanged(at=at, to=to, grant_id=grant_id, generation=generation):
            return (
                "control_changed",
                {
                    "at": at.isoformat(),
                    "to": to,
                    "grant_id": grant_id,
                    "generation": generation,
                },
                None,
            )
        case _ as unseen:
            assert_never(unseen)


def _from_row(row: ConversationEventRow) -> ConversationEvent:
    payload = json.loads(row.payload_json)
    at = datetime.fromisoformat(payload["at"])
    match row.kind:
        case "user_said":
            return UserSaid(
                seq=row.seq,
                at=at,
                text=payload["text"],
                client_id=payload["client_id"],
            )
        case "turn_started":
            return TurnStarted(
                seq=row.seq,
                at=at,
                turn_id=payload["turn_id"],
                for_message_seq=payload["for_message_seq"],
                objective=payload["objective"],
            )
        case "turn_ended":
            return TurnEnded(
                seq=row.seq,
                at=at,
                turn_id=payload["turn_id"],
                outcome=_outcome_from_payload(payload["outcome"]),
            )
        case "stage_bound":
            rebound = payload["rebound_from"]
            return StageBound(
                seq=row.seq,
                at=at,
                stage=_stage_from_payload(payload["stage"]),
                rebound_from=None if rebound is None else _stage_from_payload(rebound),
            )
        case "control_changed":
            return ControlChanged(
                seq=row.seq,
                at=at,
                to=payload["to"],
                grant_id=payload["grant_id"],
                generation=payload["generation"],
            )
        case _:
            raise ValueError(row.kind)


def _outcome_payload(outcome: TurnOutcome) -> dict:
    match outcome:
        case Done(summary=summary, data=data, items=items, final_url=final_url):
            return {
                "kind": "done",
                "summary": summary,
                "data": data,
                "items": list(items),
                "final_url": final_url,
            }
        case Asked(question=question):
            return {"kind": "asked", "question": question}
        case NeedsConfirmation(action=action, question=question):
            return {
                "kind": "needs_confirmation",
                "action": action,
                "question": question,
            }
        case HandedOff(to_grant_id=to_grant_id):
            return {"kind": "handed_off", "to_grant_id": to_grant_id}
        case Failed(reason=reason, message=message):
            return {"kind": "failed", "reason": reason, "message": message}
        case Rejected(reason=reason, message=message, retryable=retryable):
            return {
                "kind": "rejected",
                "reason": reason,
                "message": message,
                "retryable": retryable,
            }
        case _ as unseen:
            assert_never(unseen)


def _outcome_from_payload(payload: dict) -> TurnOutcome:
    match payload["kind"]:
        case "done":
            return Done(
                summary=payload["summary"],
                data=payload["data"],
                items=tuple(payload["items"]),
                final_url=payload["final_url"],
            )
        case "asked":
            return Asked(question=payload["question"])
        case "needs_confirmation":
            return NeedsConfirmation(
                action=payload["action"],
                question=payload["question"],
            )
        case "handed_off":
            return HandedOff(to_grant_id=payload["to_grant_id"])
        case "failed":
            return Failed(reason=payload["reason"], message=payload["message"])
        case "rejected":
            return Rejected(
                reason=payload["reason"],
                message=payload["message"],
                retryable=payload["retryable"],
            )
        case _:
            raise ValueError(payload["kind"])


def _stage_payload(stage: StageRef) -> dict:
    return {"value": stage.value, "kind": stage.kind}


def _stage_from_payload(payload: dict) -> StageRef:
    return StageRef(value=payload["value"], kind=payload["kind"])
