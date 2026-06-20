from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from sqlmodel import Session, select

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.crypto import encrypt
from app.db.models import Credential, Run, Trigger, Workflow, WorkflowCredential, WorkflowVersion
from app.db.session import engine
from app.integrations import load_integrations
from app.services import poll_runner as poll_svc
from app.services.variable_interpolation import resolve_params


@pytest.fixture(autouse=True)
def _fresh_registry():
    load_integrations()
    yield


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _seed_workflow(session: Session) -> tuple[str, str]:
    wf = Workflow(name=f"wf-{uuid.uuid4().hex[:6]}", created_at=_utcnow(), updated_at=_utcnow())
    session.add(wf)
    session.commit()
    session.refresh(wf)
    ver = WorkflowVersion(
        workflow_id=wf.id,
        version_index=1,
        nodes_json="[]",
        edges_json="[]",
        start_id="n1",
        authored_by="test",
        created_at=_utcnow(),
    )
    session.add(ver)
    session.commit()
    session.refresh(ver)
    wf.current_version_id = ver.id
    session.add(wf)
    session.commit()
    return wf.id, ver.id


def _make_cred(session: Session, workflow_id: str) -> str:
    name = f"fixture_key_{uuid.uuid4().hex[:8]}"
    blob = encrypt(json.dumps({"api_key": "secret"}, ensure_ascii=False).encode())
    cred = Credential(name=name, type="fixture_api_key", ciphertext=blob)
    session.add(cred)
    session.commit()
    session.refresh(cred)
    session.add(WorkflowCredential(workflow_id=workflow_id, credential_id=cred.id))
    session.commit()
    return name


def _setup_poll(
    *,
    poll_mode: str = "per_record",
    on_first_poll: str = "fire_all",
    min_poll_interval_s: int = 0,
    last_polled_at: datetime | None = None,
) -> tuple[str, str]:
    with Session(engine) as session:
        wf_id, _ = _seed_workflow(session)
        cred = _make_cred(session, wf_id)
        trig = Trigger(
            workflow_id=wf_id,
            type="poll",
            schedule_or_path="poll",
            enabled=True,
            poll_app="_fixture",
            poll_resource="records",
            poll_operation="list",
            poll_credential=cred,
            poll_dedup_path="id",
            poll_mode=poll_mode,
            on_first_poll=on_first_poll,
            min_poll_interval_s=min_poll_interval_s,
            first_poll_done=False,
            last_polled_at=last_polled_at,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        session.add(trig)
        session.commit()
        session.refresh(trig)
        return wf_id, trig.id


def _list_transport(responses: list[dict]) -> httpx.MockTransport:
    state = {"i": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        idx = min(state["i"], len(responses) - 1)
        state["i"] += 1
        return httpx.Response(200, json=responses[idx])

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_only_new_records_fire():
    transport = _list_transport(
        [
            {"data": [{"id": "A"}, {"id": "B"}]},
            {"data": [{"id": "A"}, {"id": "B"}, {"id": "C"}]},
        ]
    )
    wf_id, trig_id = _setup_poll(on_first_poll="fire_none")

    await poll_svc.tick_trigger(trig_id, transport=transport, force=True)
    with Session(engine) as session:
        assert len(session.exec(select(Run).where(Run.workflow_id == wf_id)).all()) == 0

    await poll_svc.tick_trigger(trig_id, transport=transport, force=True)
    with Session(engine) as session:
        runs = session.exec(select(Run).where(Run.workflow_id == wf_id)).all()
        assert len(runs) == 1
        ctx = json.loads(runs[0].trigger_context_json or "{}")
        assert ctx["context"]["id"] == "C"


@pytest.mark.asyncio
async def test_no_new_records_fire_nothing():
    transport = _list_transport(
        [
            {"data": [{"id": "1"}, {"id": "2"}]},
            {"data": [{"id": "1"}, {"id": "2"}]},
        ]
    )
    wf_id, trig_id = _setup_poll(on_first_poll="fire_all")

    await poll_svc.tick_trigger(trig_id, transport=transport, force=True)
    with Session(engine) as session:
        after_first = len(session.exec(select(Run).where(Run.workflow_id == wf_id)).all())
    assert after_first == 2

    await poll_svc.tick_trigger(trig_id, transport=transport, force=True)
    with Session(engine) as session:
        after_second = len(session.exec(select(Run).where(Run.workflow_id == wf_id)).all())
    assert after_second == 2


@pytest.mark.asyncio
async def test_per_record_mode():
    wf_id, trig_id = _setup_poll(poll_mode="per_record")
    transport = _list_transport([{"data": [{"id": "1"}, {"id": "2"}]}])

    await poll_svc.tick_trigger(trig_id, transport=transport, force=True)
    with Session(engine) as session:
        assert len(session.exec(select(Run).where(Run.workflow_id == wf_id)).all()) == 2


@pytest.mark.asyncio
async def test_batched_mode():
    wf_id, trig_id = _setup_poll(poll_mode="batched")
    transport = _list_transport([{"data": [{"id": "1"}, {"id": "2"}]}])

    await poll_svc.tick_trigger(trig_id, transport=transport, force=True)
    with Session(engine) as session:
        runs = session.exec(select(Run).where(Run.workflow_id == wf_id)).all()
        assert len(runs) == 1
        ctx = json.loads(runs[0].trigger_context_json or "{}")
        assert ctx["context"]["items"] == [{"id": "1"}, {"id": "2"}]


@pytest.mark.asyncio
async def test_first_poll_fire_none():
    wf_id, trig_id = _setup_poll(on_first_poll="fire_none")
    transport = _list_transport([{"data": [{"id": str(i)} for i in range(50)]}])

    await poll_svc.tick_trigger(trig_id, transport=transport, force=True)
    with Session(engine) as session:
        assert len(session.exec(select(Run).where(Run.workflow_id == wf_id)).all()) == 0
        row = session.get(Trigger, trig_id)
        assert row is not None and row.last_seen_key is not None


@pytest.mark.asyncio
async def test_first_poll_fire_latest():
    wf_id, trig_id = _setup_poll(on_first_poll="fire_latest")
    transport = _list_transport(
        [{"data": [{"id": "1"}, {"id": "9"}, {"id": "5"}]}]
    )

    await poll_svc.tick_trigger(trig_id, transport=transport, force=True)
    with Session(engine) as session:
        runs = session.exec(select(Run).where(Run.workflow_id == wf_id)).all()
        assert len(runs) == 1
        ctx = json.loads(runs[0].trigger_context_json or "{}")
        assert ctx["context"]["id"] == "9"


@pytest.mark.asyncio
async def test_interval_enforced():
    wf_id, trig_id = _setup_poll(min_poll_interval_s=3600, last_polled_at=_utcnow())
    transport = _list_transport([{"data": [{"id": "1"}]}, {"data": [{"id": "2"}]}])

    n = await poll_svc.tick_trigger(trig_id, transport=transport, force=False)
    assert n == 0


@pytest.mark.asyncio
async def test_run_context_resolves():
    ns = {"context": {"id": 7, "name": "x"}, "kind": "poll", "id": "trg-1"}
    out = resolve_params({"label": "{{run.context.name}}"}, trigger_namespace=ns)
    assert out == {"label": "x"}
    out2 = resolve_params({"kind": "{{trigger.kind}}"}, trigger_namespace=ns)
    assert out2 == {"kind": "poll"}
