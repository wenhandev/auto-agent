from __future__ import annotations

import uuid

import pytest
from sqlmodel import Session, select

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


def test_post_start_twice_returns_same_id(client, seeded):
    first = client.post("/api/conversations")
    assert first.status_code == 200
    _track(seeded, first.json()["id"])
    second = client.post("/api/conversations")
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_post_message_queues_dispatch(client, seeded):
    opened = client.post("/api/conversations")
    assert opened.status_code == 200
    conversation_id = opened.json()["id"]
    _track(seeded, conversation_id)
    result = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"text": "open notes", "client_id": "c1"},
    )
    assert result.status_code == 200
    body = result.json()
    assert body["pending_count"] == 1
    assert body["next"]["kind"] == "dispatch"
    loaded = client.get(f"/api/conversations/{conversation_id}")
    assert loaded.status_code == 200
    assert loaded.json()["pending_count"] == 1
    assert loaded.json()["next"]["kind"] == "dispatch"


def test_same_client_id_is_one_event(client, seeded):
    opened = client.post("/api/conversations")
    conversation_id = opened.json()["id"]
    _track(seeded, conversation_id)
    first = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"text": "open notes", "client_id": "c1"},
    )
    second = client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"text": "open notes", "client_id": "c1"},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert [event["seq"] for event in first.json()["events"]] == [
        event["seq"] for event in second.json()["events"]
    ]
    assert len(second.json()["events"]) == 1


def test_get_missing_id_is_404(client):
    missing = f"missing-{uuid.uuid4().hex}"
    result = client.get(f"/api/conversations/{missing}")
    assert result.status_code == 404
