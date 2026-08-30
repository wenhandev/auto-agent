from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.conversation import store
from app.conversation.model import (
    ConversationEvent,
    NextStep,
    Nobody,
    UserSaid,
    fold,
    next_step,
)
from app.db.models import Conversation
from app.db.session import engine


class ConversationNotFound(LookupError):
    def __init__(self, conversation_id: str) -> None:
        super().__init__(conversation_id)
        self.conversation_id = conversation_id


@dataclass(frozen=True, slots=True)
class ConversationView:
    id: str
    title: str
    closed: bool
    pending_count: int
    awaiting_answer: bool
    events: tuple[ConversationEvent, ...]
    control_hint: Literal["agent", "human"]
    next: NextStep


async def start(*, owner_id: str, org_id: str | None = None) -> ConversationView:
    with Session(engine) as session:
        row = store.find_open(session, owner_id)
        if row is None:
            row = store.create(session, owner_id=owner_id, org_id=org_id)
            session.commit()
            session.refresh(row)
        return _view(session, row)


async def send(
    conversation_id: str,
    *,
    text: str,
    client_id: str,
    owner_id: str | None = None,
) -> ConversationView:
    with Session(engine) as session:
        row = store.get_conversation(session, conversation_id)
        if row is None or (
            owner_id is not None and row.owner_id != owner_id
        ):
            raise ConversationNotFound(conversation_id)
        if store.find_by_client_id(session, conversation_id, client_id) is not None:
            return _view(session, row)
        events = store.list_events(session, conversation_id)
        state = fold(events)
        store.append(
            session,
            conversation_id,
            UserSaid(
                seq=state.last_seq + 1,
                at=datetime.now(timezone.utc),
                text=text,
                client_id=client_id,
            ),
        )
        row.updated_at = datetime.now(timezone.utc)
        session.add(row)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            row = store.get_conversation(session, conversation_id)
            if row is None:
                raise ConversationNotFound(conversation_id) from None
            if store.find_by_client_id(session, conversation_id, client_id) is None:
                raise
            return _view(session, row)
        session.refresh(row)
        return _view(session, row)


def view(
    conversation_id: str, *, owner_id: str | None = None
) -> ConversationView:
    with Session(engine) as session:
        row = store.get_conversation(session, conversation_id)
        if row is None or (
            owner_id is not None and row.owner_id != owner_id
        ):
            raise ConversationNotFound(conversation_id)
        return _view(session, row)


def _view(session: Session, row: Conversation) -> ConversationView:
    events = store.list_events(session, row.id)
    state = fold(events)
    return ConversationView(
        id=row.id,
        title=row.title,
        closed=row.closed_at is not None,
        pending_count=len(state.pending),
        awaiting_answer=state.awaiting_answer_to is not None,
        events=tuple(events),
        control_hint=state.control_hint,
        next=next_step(state, Nobody()),
    )
