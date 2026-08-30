from __future__ import annotations

from datetime import UTC, datetime

from app.conversation import (
    Agent,
    Asked,
    ControlChanged,
    ConversationState,
    Dispatch,
    Done,
    Hold,
    Human,
    Nobody,
    Rejected,
    StageBound,
    StageRef,
    TurnEnded,
    TurnStarted,
    UserSaid,
    fold,
    next_step,
)

AT = datetime(2026, 8, 30, tzinfo=UTC)


def _said(seq: int, text: str) -> UserSaid:
    return UserSaid(seq=seq, at=AT, text=text, client_id="c1")


def _started(seq: int, turn_id: str, for_seq: int, objective: str) -> TurnStarted:
    return TurnStarted(
        seq=seq,
        at=AT,
        turn_id=turn_id,
        for_message_seq=for_seq,
        objective=objective,
    )


def _ended(seq: int, turn_id: str, outcome: Done | Asked | Rejected) -> TurnEnded:
    return TurnEnded(seq=seq, at=AT, turn_id=turn_id, outcome=outcome)


def test_empty_holds_nothing_pending() -> None:
    state = fold(())
    assert state == ConversationState(
        last_seq=0,
        stage=None,
        active_turn_id=None,
        pending=(),
        awaiting_answer_to=None,
        control_hint="agent",
    )
    assert next_step(state, Nobody()) == Hold(why="nothing_pending")


def test_one_user_said_dispatches() -> None:
    state = fold((_said(1, "open notes"),))
    assert state.pending == ((1, "open notes"),)
    assert next_step(state, Nobody()) == Dispatch(
        message_seq=1,
        objective="open notes",
        continues_turn_id=None,
        stage=None,
    )


def test_started_turn_holds_running() -> None:
    events = (_said(1, "open notes"), _started(2, "t1", 1, "open notes"))
    state = fold(events)
    assert state.active_turn_id == "t1"
    assert state.pending == ()
    assert next_step(state, Nobody()) == Hold(why="turn_running")
    assert next_step(state, Agent(turn_id="t1", generation=0)) == Hold(why="turn_running")


def test_queue_while_running_keeps_second_pending() -> None:
    events = (
        _said(1, "first"),
        _said(2, "second"),
        _started(3, "t1", 1, "first"),
    )
    state = fold(events)
    assert state.pending == ((2, "second"),)
    assert state.active_turn_id == "t1"
    assert next_step(state, Nobody()) == Hold(why="turn_running")


def test_done_then_dispatch_second() -> None:
    events = (
        _said(1, "first"),
        _said(2, "second"),
        _started(3, "t1", 1, "first"),
        _ended(4, "t1", Done(summary="ok", data=None, items=(), final_url=None)),
    )
    state = fold(events)
    assert state.active_turn_id is None
    assert state.pending == ((2, "second"),)
    assert next_step(state, Nobody()) == Dispatch(
        message_seq=2,
        objective="second",
        continues_turn_id=None,
        stage=None,
    )


def test_human_driver_holds_even_with_pending() -> None:
    events = (
        _said(1, "open notes"),
        ControlChanged(seq=2, at=AT, to="human", grant_id="g1", generation=1),
    )
    state = fold(events)
    assert state.control_hint == "human"
    assert state.pending == ((1, "open notes"),)
    assert next_step(
        state,
        Human(grant_id="g1", since=AT, generation=1),
    ) == Hold(why="human_driving")


def test_release_to_agent_dispatches() -> None:
    events = (
        _said(1, "open notes"),
        ControlChanged(seq=2, at=AT, to="human", grant_id="g1", generation=1),
        ControlChanged(seq=3, at=AT, to="agent", grant_id="g1", generation=2),
    )
    state = fold(events)
    assert state.control_hint == "agent"
    assert next_step(state, Nobody()) == Dispatch(
        message_seq=1,
        objective="open notes",
        continues_turn_id=None,
        stage=None,
    )


def test_retryable_reject_returns_message_to_pending() -> None:
    events = (
        _said(1, "open notes"),
        _started(2, "t1", 1, "open notes"),
        _ended(3, "t1", Rejected(reason="stage_busy", message="busy", retryable=True)),
    )
    state = fold(events)
    assert state.active_turn_id is None
    assert state.pending == ((1, "open notes"),)
    assert next_step(state, Nobody()) == Dispatch(
        message_seq=1,
        objective="open notes",
        continues_turn_id=None,
        stage=None,
    )


def test_non_retryable_reject_consumes_message() -> None:
    events = (
        _said(1, "open notes"),
        _started(2, "t1", 1, "open notes"),
        _ended(3, "t1", Rejected(reason="not_approved", message="denied", retryable=False)),
    )
    state = fold(events)
    assert state.pending == ()
    assert next_step(state, Nobody()) == Hold(why="nothing_pending")


def test_asked_then_new_message_continues_turn() -> None:
    events = (
        _said(1, "book a flight"),
        _started(2, "t1", 1, "book a flight"),
        _ended(3, "t1", Asked(question="which city?")),
        _said(4, "tokyo"),
    )
    state = fold(events)
    assert state.awaiting_answer_to == "t1"
    assert state.pending == ((4, "tokyo"),)
    assert next_step(state, Nobody()) == Dispatch(
        message_seq=4,
        objective="tokyo",
        continues_turn_id="t1",
        stage=None,
    )


def test_stage_rebind_keeps_latest_ref() -> None:
    old = StageRef(value="safari", kind="browser")
    new = StageRef(value="notes", kind="desktop_app")
    events = (
        StageBound(seq=1, at=AT, stage=old, rebound_from=None),
        StageBound(seq=2, at=AT, stage=new, rebound_from=old),
    )
    state = fold(events)
    assert state.stage == new


def test_control_changed_generation_is_not_interpreted() -> None:
    events = (
        _said(1, "open notes"),
        ControlChanged(seq=2, at=AT, to="agent", grant_id="g1", generation=7),
    )
    state = fold(events)
    assert state.control_hint == "agent"
    assert not hasattr(state, "generation")
    expected = Dispatch(
        message_seq=1,
        objective="open notes",
        continues_turn_id=None,
        stage=None,
    )
    assert next_step(state, Nobody()) == expected
    assert next_step(state, Agent(turn_id="t1", generation=7)) == expected
    assert next_step(state, Agent(turn_id="t1", generation=1)) == expected
