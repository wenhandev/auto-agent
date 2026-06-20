"""Cron scheduling: timezone, enable/disable, next_run_at, misfire policy, org scope."""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.models import Organization, Trigger, Workflow, WorkflowVersion
from app.db.session import engine
from app.main import app
from app.services import scheduler as scheduler_svc
from app.services import trigger_scheduling as sched_svc


client = TestClient(app)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _seed_workflow(session: Session, *, org_id: str | None = None) -> str:
    wf = Workflow(
        name=f"wf-{uuid.uuid4().hex[:6]}",
        org_id=org_id,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    session.add(wf)
    session.commit()
    session.refresh(wf)
    ver = WorkflowVersion(
        workflow_id=wf.id,
        version_index=1,
        nodes_json='[{"id":"start","type":"start","label":"S","params":{}}]',
        edges_json="[]",
        start_id="start",
        authored_by="test",
        created_at=_utcnow(),
    )
    session.add(ver)
    session.commit()
    session.refresh(ver)
    wf.current_version_id = ver.id
    session.add(wf)
    session.commit()
    return wf.id


def _create_org(session: Session, name: str) -> Organization:
    org = Organization(name=name, created_at=_utcnow())
    session.add(org)
    session.commit()
    session.refresh(org)
    return org


def test_validate_cron_rejects_bad_expression():
    assert sched_svc.validate_cron("not a cron", "UTC") is not None


def test_validate_timezone_rejects_unknown():
    assert sched_svc.validate_timezone("Not/A/Zone") is not None


def test_compute_next_fires_returns_ordered_datetimes():
    fires = sched_svc.compute_next_fires("0 9 * * *", "Asia/Shanghai", n=3)
    assert len(fires) == 3
    assert fires[0] < fires[1] < fires[2]


def test_create_cron_trigger_with_timezone():
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
    resp = client.post(
        f"/api/workflows/{wf_id}/triggers",
        json={
            "type": "cron",
            "schedule_or_path": "0 9 * * *",
            "timezone": "Asia/Shanghai",
            "enabled": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["timezone"] == "Asia/Shanghai"
    assert data["misfire_policy"] == "skip"


def test_create_cron_rejects_invalid_expression():
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
    resp = client.post(
        f"/api/workflows/{wf_id}/triggers",
        json={"type": "cron", "schedule_or_path": "not a cron"},
    )
    assert resp.status_code == 422


def test_create_cron_rejects_invalid_timezone():
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
    resp = client.post(
        f"/api/workflows/{wf_id}/triggers",
        json={
            "type": "cron",
            "schedule_or_path": "0 9 * * *",
            "timezone": "Invalid/Zone",
        },
    )
    assert resp.status_code == 422


def test_disable_cron_removes_scheduler_job():
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
    with patch.object(scheduler_svc, "unregister_trigger") as unreg, patch.object(
        scheduler_svc, "register_trigger"
    ) as reg:
        create = client.post(
            f"/api/workflows/{wf_id}/triggers",
            json={
                "type": "cron",
                "schedule_or_path": "*/5 * * * *",
                "enabled": True,
            },
        )
        trig_id = create.json()["id"]
        reg.assert_called_once()

        disable = client.patch(
            f"/api/triggers/{trig_id}",
            json={"enabled": False},
        )
        assert disable.status_code == 200
        unreg.assert_called_with(trig_id)
        assert reg.call_count == 1

    with Session(engine) as session:
        trig = session.get(Trigger, trig_id)
        assert trig is not None
        assert trig.next_run_at is None


def test_enable_cron_restores_scheduler_job():
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
    with patch.object(scheduler_svc, "unregister_trigger"), patch.object(
        scheduler_svc, "register_trigger"
    ) as reg:
        create = client.post(
            f"/api/workflows/{wf_id}/triggers",
            json={"type": "cron", "schedule_or_path": "*/5 * * * *", "enabled": False},
        )
        trig_id = create.json()["id"]
        reg.assert_not_called()

        enable = client.patch(f"/api/triggers/{trig_id}", json={"enabled": True})
        assert enable.status_code == 200
        reg.assert_called_once()
        assert enable.json()["next_run_at"] is not None


def test_next_fires_preview_endpoint():
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
    create = client.post(
        f"/api/workflows/{wf_id}/triggers",
        json={"type": "cron", "schedule_or_path": "0 9 * * *", "timezone": "UTC"},
    )
    trig_id = create.json()["id"]
    resp = client.get(f"/api/triggers/{trig_id}/next-fires?n=3")
    assert resp.status_code == 200
    body = resp.json()
    assert body["trigger_id"] == trig_id
    assert body["timezone"] == "UTC"
    assert len(body["fires"]) == 3


def test_misfire_policy_catch_up_stored_and_registered():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    with Session(engine) as session:
        wf_id = _seed_workflow(session)
        trig = Trigger(
            workflow_id=wf_id,
            type="cron",
            schedule_or_path="*/10 * * * *",
            enabled=True,
            misfire_policy="catch_up",
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        session.add(trig)
        session.commit()
        session.refresh(trig)

    fake_sched = AsyncIOScheduler(timezone="UTC")
    with patch.object(scheduler_svc, "_scheduler", fake_sched):
        scheduler_svc._register_cron_trigger(trig)
        job = fake_sched.get_job(f"trigger:{trig.id}")
        assert job is not None
        assert job.misfire_grace_time is None
        assert job.coalesce is False


def test_fire_sets_last_fired_at_before_enqueue():
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
        trig = Trigger(
            workflow_id=wf_id,
            type="cron",
            schedule_or_path="*/5 * * * *",
            enabled=True,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        session.add(trig)
        session.commit()
        session.refresh(trig)
        trig_id = trig.id

    order: list[str] = []

    def fake_enqueue(*args, **kwargs):
        with Session(engine) as session:
            row = session.get(Trigger, trig_id)
            assert row is not None
            assert row.last_fired_at is not None
            order.append("enqueue")
        return None

    with patch(
        "app.services.runs.enqueue_run_standalone", side_effect=fake_enqueue
    ):
        scheduler_svc._fire_trigger(trig_id)

    assert order == ["enqueue"]


def test_regenerate_secret_workflow_scoped_endpoint():
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
    path = f"orders-{uuid.uuid4().hex[:8]}"
    create = client.post(
        f"/api/workflows/{wf_id}/triggers",
        json={"type": "webhook", "schedule_or_path": path},
    )
    assert create.status_code == 200
    trig_id = create.json()["id"]
    assert create.json()["secret_full"] is not None

    regen = client.post(
        f"/api/workflows/{wf_id}/triggers/{trig_id}/regenerate-secret"
    )
    assert regen.status_code == 200
    assert regen.json()["secret_full"] is not None

    detail = client.get(f"/api/workflows/{wf_id}/triggers")
    row = next(t for t in detail.json() if t["id"] == trig_id)
    assert row.get("secret_full") is None
    assert row.get("secret_masked")


def test_trigger_org_scoping_denies_cross_org():
    with Session(engine) as session:
        org_a = _create_org(session, f"org-a-{uuid.uuid4().hex[:4]}")
        org_b = _create_org(session, f"org-b-{uuid.uuid4().hex[:4]}")
        org_a_id = org_a.id
        org_b_id = org_b.id
        wf_a = _seed_workflow(session, org_id=org_a_id)
        wf_b = _seed_workflow(session, org_id=org_b_id)

    create = client.post(
        f"/api/workflows/{wf_a}/triggers",
        headers={"x-org-id": org_a_id},
        json={"type": "cron", "schedule_or_path": "0 9 * * *"},
    )
    trig_id = create.json()["id"]

    denied_list = client.get(
        f"/api/workflows/{wf_a}/triggers",
        headers={"x-org-id": org_b_id},
    )
    assert denied_list.status_code == 404

    denied_update = client.patch(
        f"/api/triggers/{trig_id}",
        headers={"x-org-id": org_b_id},
        json={"enabled": False},
    )
    assert denied_update.status_code == 404

    denied_other_wf = client.put(
        f"/api/workflows/{wf_b}/triggers/{trig_id}",
        headers={"x-org-id": org_b_id},
        json={"enabled": False},
    )
    assert denied_other_wf.status_code == 404


def test_misfire_grace_skip_vs_catch_up():
    assert sched_svc.misfire_grace_time("skip") == sched_svc.MISFIRE_GRACE_SECONDS
    assert sched_svc.misfire_grace_time("catch_up") is None


def test_select_triggers_for_boot_caps_and_skips_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    now = _utcnow()
    stale = now - timedelta(days=60)
    recent = now - timedelta(days=1)
    rows = [
        Trigger(
            id=f"t{i}",
            workflow_id="wf-a",
            type="poll",
            schedule_or_path="poll",
            enabled=True,
            created_at=stale if i < 3 else recent,
            updated_at=stale if i < 3 else recent,
        )
        for i in range(5)
    ]
    monkeypatch.setattr("app.services.scheduler.settings.trigger_max_active", 2)
    monkeypatch.setattr("app.services.scheduler.settings.trigger_stale_days", 30)
    monkeypatch.setattr("app.services.scheduler.settings.trigger_max_poll_per_workflow", 10)

    selected = scheduler_svc.select_triggers_for_boot(rows)
    assert len(selected) == 2
    assert all(trig.created_at >= recent - timedelta(seconds=1) for trig in selected)


def test_select_triggers_for_boot_poll_per_workflow_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    now = _utcnow()
    rows = [
        Trigger(
            id=f"p{i}",
            workflow_id="wf-a" if i < 3 else "wf-b",
            type="poll",
            schedule_or_path="poll",
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        for i in range(5)
    ]
    monkeypatch.setattr("app.services.scheduler.settings.trigger_max_active", 50)
    monkeypatch.setattr("app.services.scheduler.settings.trigger_stale_days", 0)
    monkeypatch.setattr("app.services.scheduler.settings.trigger_max_poll_per_workflow", 2)

    selected = scheduler_svc.select_triggers_for_boot(rows)
    assert len(selected) == 4
    assert sum(1 for t in selected if t.workflow_id == "wf-a") == 2
    assert sum(1 for t in selected if t.workflow_id == "wf-b") == 2
