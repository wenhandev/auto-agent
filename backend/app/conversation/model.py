from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Sequence, assert_never

StageKind = Literal["browser", "desktop_app"]


@dataclass(frozen=True, slots=True)
class StageRef:
    value: str
    kind: StageKind


@dataclass(frozen=True, slots=True)
class Nobody:
    pass


@dataclass(frozen=True, slots=True)
class Agent:
    turn_id: str
    generation: int


@dataclass(frozen=True, slots=True)
class Human:
    grant_id: str
    since: datetime
    generation: int


Driver = Nobody | Agent | Human


@dataclass(frozen=True, slots=True)
class Done:
    summary: str
    data: object | None
    items: tuple[object, ...]
    final_url: str | None


@dataclass(frozen=True, slots=True)
class Asked:
    question: str


@dataclass(frozen=True, slots=True)
class NeedsConfirmation:
    action: str
    question: str


@dataclass(frozen=True, slots=True)
class HandedOff:
    to_grant_id: str


@dataclass(frozen=True, slots=True)
class Failed:
    reason: Literal["guardrail", "budget", "no_progress", "error", "aborted"]
    message: str


@dataclass(frozen=True, slots=True)
class Rejected:
    reason: Literal["stage_unavailable", "stage_busy", "worker_unavailable", "not_approved"]
    message: str
    retryable: bool


TurnOutcome = Done | Asked | NeedsConfirmation | HandedOff | Failed | Rejected


@dataclass(frozen=True, slots=True)
class UserSaid:
    seq: int
    at: datetime
    text: str
    client_id: str


@dataclass(frozen=True, slots=True)
class TurnStarted:
    seq: int
    at: datetime
    turn_id: str
    for_message_seq: int
    objective: str


@dataclass(frozen=True, slots=True)
class TurnEnded:
    seq: int
    at: datetime
    turn_id: str
    outcome: TurnOutcome


@dataclass(frozen=True, slots=True)
class StageBound:
    seq: int
    at: datetime
    stage: StageRef
    rebound_from: StageRef | None


@dataclass(frozen=True, slots=True)
class ControlChanged:
    seq: int
    at: datetime
    to: Literal["human", "agent"]
    grant_id: str
    generation: int


ConversationEvent = UserSaid | TurnStarted | TurnEnded | StageBound | ControlChanged


@dataclass(frozen=True, slots=True)
class ConversationState:
    last_seq: int
    stage: StageRef | None
    active_turn_id: str | None
    pending: tuple[tuple[int, str], ...]
    awaiting_answer_to: str | None
    control_hint: Literal["agent", "human"]


@dataclass(frozen=True, slots=True)
class Dispatch:
    message_seq: int
    objective: str
    continues_turn_id: str | None
    stage: StageRef | None


@dataclass(frozen=True, slots=True)
class Hold:
    why: Literal["turn_running", "human_driving", "nothing_pending", "closed"]


NextStep = Dispatch | Hold


def fold(events: Sequence[ConversationEvent]) -> ConversationState:
    last_seq = 0
    stage: StageRef | None = None
    open_turns: list[str] = []
    said: list[tuple[int, str]] = []
    claimed: set[int] = set()
    turn_message: dict[str, int] = {}
    awaiting_answer_to: str | None = None
    control_hint: Literal["agent", "human"] = "agent"

    for event in events:
        last_seq = max(last_seq, event.seq)
        match event:
            case UserSaid(seq=seq, text=text):
                said.append((seq, text))
            case TurnStarted(turn_id=turn_id, for_message_seq=for_message_seq):
                claimed.add(for_message_seq)
                turn_message[turn_id] = for_message_seq
                open_turns.append(turn_id)
            case TurnEnded(turn_id=turn_id, outcome=outcome):
                if turn_id in open_turns:
                    open_turns.remove(turn_id)
                if isinstance(outcome, Rejected) and outcome.retryable:
                    message_seq = turn_message.get(turn_id)
                    if message_seq is not None:
                        claimed.discard(message_seq)
                elif isinstance(outcome, (Asked, NeedsConfirmation)):
                    awaiting_answer_to = turn_id
                else:
                    awaiting_answer_to = None
            case StageBound(stage=bound):
                stage = bound
            case ControlChanged(to=to):
                control_hint = to
            case _ as unseen:
                assert_never(unseen)

    return ConversationState(
        last_seq=last_seq,
        stage=stage,
        active_turn_id=open_turns[-1] if open_turns else None,
        pending=tuple(item for item in said if item[0] not in claimed),
        awaiting_answer_to=awaiting_answer_to,
        control_hint=control_hint,
    )


def next_step(state: ConversationState, driver: Driver) -> NextStep:
    if isinstance(driver, Human):
        return Hold(why="human_driving")
    if state.active_turn_id is not None:
        return Hold(why="turn_running")
    if not state.pending:
        return Hold(why="nothing_pending")
    message_seq, objective = state.pending[0]
    return Dispatch(
        message_seq=message_seq,
        objective=objective,
        continues_turn_id=state.awaiting_answer_to,
        stage=state.stage,
    )
