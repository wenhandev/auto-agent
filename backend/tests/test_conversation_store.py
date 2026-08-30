from __future__ import annotations

import uuid

import pytest
from sqlmodel import Session, select

from app.conversation.model import Dispatch, UserSaid
from app.conversation.service import ConversationNotFound, send, start, view
from app.db.models import Conversation, ConversationEventRow
from app.db.session import engine, init_db


@pytest.fixture(autouse=True)
def _ensure_schema():
    init_db()
    yield


@pytest.fixture
def seeded():
    ids: list[str] = []
    yield ids
    with Session(engine) as session:
        _delete_conversations(session, ids)


def _delete_conversations(session: Session, ids: list[str]) -> None:
    for conversation_id in ids:
        for ev in session.exec(
            select(ConversationEventRow).where(
                ConversationEventRow.conversation_id == conversation_id
            )
        ).all():
            session.delete(ev)
        row = session.get(Conversation, conversation_id)
        if row is not None:
            session.delete(row)
    session.commit()


def _track(ids: list[str], conversation_id: str) -> None:
    if conversation_id not in ids:
        ids.append(conversation_id)


@pytest.mark.asyncio
async def test_start_twice_resumes_same_id(seeded):
    owner_id = f"owner-{uuid.uuid4().hex}"
    first = await start(owner_id=owner_id)
    _track(seeded, first.id)
    second = await start(owner_id=owner_id)
    assert first.id == second.id


@pytest.mark.asyncio
async def test_send_appends_user_said_and_would_dispatch(seeded):
    owner_id = f"owner-{uuid.uuid4().hex}"
    opened = await start(owner_id=owner_id)
    _track(seeded, opened.id)
    result = await send(opened.id, text="open notes", client_id="c1")
    assert result.pending_count == 1
    assert isinstance(result.next, Dispatch)
    assert result.next == Dispatch(
        message_seq=1,
        objective="open notes",
        continues_turn_id=None,
        stage=None,
    )
    assert len(result.events) == 1
    assert isinstance(result.events[0], UserSaid)
    assert result.events[0].text == "open notes"
    assert result.events[0].client_id == "c1"
    loaded = view(opened.id)
    assert loaded.pending_count == 1
    assert isinstance(loaded.next, Dispatch)


@pytest.mark.asyncio
async def test_send_same_client_id_is_idempotent(seeded):
    owner_id = f"owner-{uuid.uuid4().hex}"
    opened = await start(owner_id=owner_id)
    _track(seeded, opened.id)
    first = await send(opened.id, text="open notes", client_id="c1")
    second = await send(opened.id, text="open notes", client_id="c1")
    assert [event.seq for event in first.events] == [event.seq for event in second.events]
    assert len(second.events) == 1


@pytest.mark.asyncio
async def test_two_sends_queue_and_dispatch_first(seeded):
    owner_id = f"owner-{uuid.uuid4().hex}"
    opened = await start(owner_id=owner_id)
    _track(seeded, opened.id)
    await send(opened.id, text="first", client_id="c1")
    result = await send(opened.id, text="second", client_id="c2")
    assert result.pending_count == 2
    assert result.next == Dispatch(
        message_seq=1,
        objective="first",
        continues_turn_id=None,
        stage=None,
    )


@pytest.mark.asyncio
async def test_unknown_conversation_raises_typed_error():
    missing = f"missing-{uuid.uuid4().hex}"
    with pytest.raises(ConversationNotFound):
        view(missing)
    with pytest.raises(ConversationNotFound):
        await send(missing, text="hello", client_id="c1")


@pytest.mark.asyncio
async def test_other_owner_cannot_view_or_send(seeded):
    owner_id = f"owner-{uuid.uuid4().hex}"
    opened = await start(owner_id=owner_id)
    _track(seeded, opened.id)
    with pytest.raises(ConversationNotFound):
        view(opened.id, owner_id="someone-else")
    with pytest.raises(ConversationNotFound):
        await send(
            opened.id,
            text="hello",
            client_id="c1",
            owner_id="someone-else",
        )
