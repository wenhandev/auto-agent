from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union, assert_never

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from app.auth.authorization import AuthContext
from app.auth.context import get_org_context
from app.conversation.model import (
    Asked,
    ControlChanged,
    ConversationEvent,
    Dispatch,
    Done,
    Failed,
    HandedOff,
    Hold,
    NeedsConfirmation,
    NextStep,
    Rejected,
    StageBound,
    StageRef,
    TurnEnded,
    TurnOutcome,
    TurnStarted,
    UserSaid,
)
from app.conversation.service import ConversationNotFound, ConversationView
from app.conversation.service import send as send_message
from app.conversation.service import start as start_conversation
from app.conversation.service import view as load_conversation
from app.schemas_api import _ApiModel


router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class ConversationMessageIn(_ApiModel):
    text: str = Field(min_length=1, max_length=8000)
    client_id: str = Field(min_length=1, max_length=64)


class StageRefOut(_ApiModel):
    value: str
    kind: Literal["browser", "desktop_app"]


class UserSaidOut(_ApiModel):
    kind: Literal["user_said"]
    seq: int
    at: datetime
    text: str
    client_id: str


class TurnStartedOut(_ApiModel):
    kind: Literal["turn_started"]
    seq: int
    at: datetime
    turn_id: str
    for_message_seq: int
    objective: str


class DoneOut(_ApiModel):
    kind: Literal["done"]
    summary: str
    data: object | None
    items: list[object]
    final_url: str | None


class AskedOut(_ApiModel):
    kind: Literal["asked"]
    question: str


class NeedsConfirmationOut(_ApiModel):
    kind: Literal["needs_confirmation"]
    action: str
    question: str


class HandedOffOut(_ApiModel):
    kind: Literal["handed_off"]
    to_grant_id: str


class FailedOut(_ApiModel):
    kind: Literal["failed"]
    reason: Literal["guardrail", "budget", "no_progress", "error", "aborted"]
    message: str


class RejectedOut(_ApiModel):
    kind: Literal["rejected"]
    reason: Literal["stage_unavailable", "stage_busy", "worker_unavailable", "not_approved"]
    message: str
    retryable: bool


TurnOutcomeOut = Annotated[
    Union[DoneOut, AskedOut, NeedsConfirmationOut, HandedOffOut, FailedOut, RejectedOut],
    Field(discriminator="kind"),
]


class TurnEndedOut(_ApiModel):
    kind: Literal["turn_ended"]
    seq: int
    at: datetime
    turn_id: str
    outcome: TurnOutcomeOut


class StageBoundOut(_ApiModel):
    kind: Literal["stage_bound"]
    seq: int
    at: datetime
    stage: StageRefOut
    rebound_from: StageRefOut | None


class ControlChangedOut(_ApiModel):
    kind: Literal["control_changed"]
    seq: int
    at: datetime
    to: Literal["human", "agent"]
    grant_id: str
    generation: int


ConversationEventOut = Annotated[
    Union[UserSaidOut, TurnStartedOut, TurnEndedOut, StageBoundOut, ControlChangedOut],
    Field(discriminator="kind"),
]


class DispatchOut(_ApiModel):
    kind: Literal["dispatch"]
    message_seq: int
    objective: str
    continues_turn_id: str | None
    stage: StageRefOut | None


class HoldOut(_ApiModel):
    kind: Literal["hold"]
    why: Literal["turn_running", "human_driving", "nothing_pending", "closed"]


NextStepOut = Annotated[Union[DispatchOut, HoldOut], Field(discriminator="kind")]


class ConversationViewOut(_ApiModel):
    id: str
    title: str
    closed: bool
    pending_count: int
    awaiting_answer: bool
    events: list[ConversationEventOut]
    control_hint: Literal["agent", "human"]
    next: NextStepOut


def _owner_id(ctx: AuthContext) -> str:
    return ctx.user_id or ctx.org_id


def _stage_out(stage: StageRef) -> StageRefOut:
    return StageRefOut(value=stage.value, kind=stage.kind)


def _outcome_out(outcome: TurnOutcome) -> TurnOutcomeOut:
    match outcome:
        case Done(summary=summary, data=data, items=items, final_url=final_url):
            return DoneOut(
                kind="done",
                summary=summary,
                data=data,
                items=list(items),
                final_url=final_url,
            )
        case Asked(question=question):
            return AskedOut(kind="asked", question=question)
        case NeedsConfirmation(action=action, question=question):
            return NeedsConfirmationOut(
                kind="needs_confirmation",
                action=action,
                question=question,
            )
        case HandedOff(to_grant_id=to_grant_id):
            return HandedOffOut(kind="handed_off", to_grant_id=to_grant_id)
        case Failed(reason=reason, message=message):
            return FailedOut(kind="failed", reason=reason, message=message)
        case Rejected(reason=reason, message=message, retryable=retryable):
            return RejectedOut(
                kind="rejected",
                reason=reason,
                message=message,
                retryable=retryable,
            )
        case _ as unseen:
            assert_never(unseen)


def _event_out(event: ConversationEvent) -> ConversationEventOut:
    match event:
        case UserSaid(seq=seq, at=at, text=text, client_id=client_id):
            return UserSaidOut(
                kind="user_said",
                seq=seq,
                at=at,
                text=text,
                client_id=client_id,
            )
        case TurnStarted(
            seq=seq,
            at=at,
            turn_id=turn_id,
            for_message_seq=for_message_seq,
            objective=objective,
        ):
            return TurnStartedOut(
                kind="turn_started",
                seq=seq,
                at=at,
                turn_id=turn_id,
                for_message_seq=for_message_seq,
                objective=objective,
            )
        case TurnEnded(seq=seq, at=at, turn_id=turn_id, outcome=outcome):
            return TurnEndedOut(
                kind="turn_ended",
                seq=seq,
                at=at,
                turn_id=turn_id,
                outcome=_outcome_out(outcome),
            )
        case StageBound(seq=seq, at=at, stage=stage, rebound_from=rebound_from):
            return StageBoundOut(
                kind="stage_bound",
                seq=seq,
                at=at,
                stage=_stage_out(stage),
                rebound_from=(
                    None if rebound_from is None else _stage_out(rebound_from)
                ),
            )
        case ControlChanged(
            seq=seq,
            at=at,
            to=to,
            grant_id=grant_id,
            generation=generation,
        ):
            return ControlChangedOut(
                kind="control_changed",
                seq=seq,
                at=at,
                to=to,
                grant_id=grant_id,
                generation=generation,
            )
        case _ as unseen:
            assert_never(unseen)


def _next_out(step: NextStep) -> NextStepOut:
    match step:
        case Dispatch(
            message_seq=message_seq,
            objective=objective,
            continues_turn_id=continues_turn_id,
            stage=stage,
        ):
            return DispatchOut(
                kind="dispatch",
                message_seq=message_seq,
                objective=objective,
                continues_turn_id=continues_turn_id,
                stage=None if stage is None else _stage_out(stage),
            )
        case Hold(why=why):
            return HoldOut(kind="hold", why=why)
        case _ as unseen:
            assert_never(unseen)


def _view_out(view: ConversationView) -> ConversationViewOut:
    return ConversationViewOut(
        id=view.id,
        title=view.title,
        closed=view.closed,
        pending_count=view.pending_count,
        awaiting_answer=view.awaiting_answer,
        events=[_event_out(event) for event in view.events],
        control_hint=view.control_hint,
        next=_next_out(view.next),
    )


def _not_found(exc: ConversationNotFound) -> HTTPException:
    return HTTPException(status_code=404, detail="not found")


@router.post("", response_model=ConversationViewOut)
async def create_conversation(
    ctx: AuthContext = Depends(get_org_context),
) -> ConversationViewOut:
    view = await start_conversation(owner_id=_owner_id(ctx), org_id=ctx.org_id)
    return _view_out(view)


@router.get("/{conversation_id}", response_model=ConversationViewOut)
def get_conversation(
    conversation_id: str,
    ctx: AuthContext = Depends(get_org_context),
) -> ConversationViewOut:
    try:
        return _view_out(
            load_conversation(conversation_id, owner_id=_owner_id(ctx))
        )
    except ConversationNotFound as exc:
        raise _not_found(exc) from exc


@router.post("/{conversation_id}/messages", response_model=ConversationViewOut)
async def post_message(
    conversation_id: str,
    body: ConversationMessageIn,
    ctx: AuthContext = Depends(get_org_context),
) -> ConversationViewOut:
    try:
        view = await send_message(
            conversation_id,
            text=body.text,
            client_id=body.client_id,
            owner_id=_owner_id(ctx),
        )
    except ConversationNotFound as exc:
        raise _not_found(exc) from exc
    return _view_out(view)
