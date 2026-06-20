"""Per-workflow credential link API and runtime enforcement tests."""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.models import Credential, Workflow, WorkflowCredential, WorkflowVersion
from app.db.session import engine, init_db
from app.main import app
from app.services.credential_interpolation import (
    CredentialResolutionError,
    resolve_params,
)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _seed_workflow(session: Session, *, name: str | None = None) -> str:
    wf = Workflow(
        name=name or f"wf-{uuid.uuid4().hex[:8]}",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(wf)
    session.commit()
    session.refresh(wf)
    version = WorkflowVersion(
        workflow_id=wf.id,
        version_index=1,
        nodes_json="[]",
        edges_json="[]",
        start_id="s",
        authored_by="manual",
    )
    session.add(version)
    session.commit()
    session.refresh(version)
    wf.current_version_id = version.id
    session.add(wf)
    session.commit()
    return wf.id


def _create_cred(client: TestClient, *, name: str) -> dict:
    resp = client.post(
        "/api/credentials",
        json={
            "name": name,
            "description": f"desc for {name}",
            "fields": {"username": f"user-{name}", "password": "secret"},
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_list_linked_credentials_empty(client: TestClient) -> None:
    init_db()
    with Session(engine) as session:
        wf_id = _seed_workflow(session)

    resp = client.get(f"/api/workflows/{wf_id}/credentials")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_linked_credentials_missing_workflow(client: TestClient) -> None:
    resp = client.get("/api/workflows/wf-missing/credentials")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "workflow not found"


def test_link_unlink_and_list_credentials(client: TestClient) -> None:
    init_db()
    with Session(engine) as session:
        wf_id = _seed_workflow(session, name="alpha-workflow")

    cred_a = _create_cred(client, name=f"cred-a-{uuid.uuid4().hex[:6]}")
    cred_b = _create_cred(client, name=f"cred-b-{uuid.uuid4().hex[:6]}")

    link_a = client.post(
        f"/api/workflows/{wf_id}/credentials",
        json={"credential_id": cred_a["id"]},
    )
    assert link_a.status_code == 200
    body_a = link_a.json()
    assert body_a["id"] == cred_a["id"]
    assert body_a["name"] == cred_a["name"]
    assert body_a["usage_count"] == 1
    assert "username" in body_a["field_names"]

    link_b = client.post(
        f"/api/workflows/{wf_id}/credentials",
        json={"credential_id": cred_b["id"]},
    )
    assert link_b.status_code == 200

    listed = client.get(f"/api/workflows/{wf_id}/credentials")
    assert listed.status_code == 200
    items = listed.json()
    assert [i["id"] for i in items] == sorted(
        [cred_a["id"], cred_b["id"]],
        key=lambda cid: next(i["name"] for i in items if i["id"] == cid),
    )
    names = [i["name"] for i in items]
    assert names == sorted(names)

    unlink = client.delete(
        f"/api/workflows/{wf_id}/credentials/{cred_a['id']}"
    )
    assert unlink.status_code == 204

    remaining = client.get(f"/api/workflows/{wf_id}/credentials")
    assert remaining.status_code == 200
    assert len(remaining.json()) == 1
    assert remaining.json()[0]["id"] == cred_b["id"]


def test_duplicate_link_returns_409(client: TestClient) -> None:
    init_db()
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
    cred = _create_cred(client, name=f"dup-{uuid.uuid4().hex[:6]}")

    first = client.post(
        f"/api/workflows/{wf_id}/credentials",
        json={"credential_id": cred["id"]},
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/workflows/{wf_id}/credentials",
        json={"credential_id": cred["id"]},
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "credential already linked to this workflow"


def test_link_missing_workflow_or_credential(client: TestClient) -> None:
    cred = _create_cred(client, name=f"orphan-{uuid.uuid4().hex[:6]}")

    missing_wf = client.post(
        "/api/workflows/wf-missing/credentials",
        json={"credential_id": cred["id"]},
    )
    assert missing_wf.status_code == 404
    assert missing_wf.json()["detail"] == "workflow not found"

    init_db()
    with Session(engine) as session:
        wf_id = _seed_workflow(session)

    missing_cred = client.post(
        f"/api/workflows/{wf_id}/credentials",
        json={"credential_id": "cred-does-not-exist"},
    )
    assert missing_cred.status_code == 404
    assert missing_cred.json()["detail"] == "credential not found"


def test_unlink_missing_link_returns_404(client: TestClient) -> None:
    init_db()
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
    cred = _create_cred(client, name=f"unlink-{uuid.uuid4().hex[:6]}")

    resp = client.delete(
        f"/api/workflows/{wf_id}/credentials/{cred['id']}"
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "credential not linked to workflow"


def test_usage_count_on_global_list(client: TestClient) -> None:
    init_db()
    with Session(engine) as session:
        wf_a = _seed_workflow(session)
        wf_b = _seed_workflow(session)
    cred = _create_cred(client, name=f"usage-{uuid.uuid4().hex[:6]}")

    listed = client.get("/api/credentials").json()
    by_id = {row["id"]: row for row in listed}
    assert by_id[cred["id"]]["usage_count"] == 0

    client.post(
        f"/api/workflows/{wf_a}/credentials",
        json={"credential_id": cred["id"]},
    )
    client.post(
        f"/api/workflows/{wf_b}/credentials",
        json={"credential_id": cred["id"]},
    )

    listed2 = client.get("/api/credentials").json()
    by_id2 = {row["id"]: row for row in listed2}
    assert by_id2[cred["id"]]["usage_count"] == 2


def test_delete_credential_removes_links(client: TestClient) -> None:
    init_db()
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
    cred = _create_cred(client, name=f"delete-{uuid.uuid4().hex[:6]}")
    client.post(
        f"/api/workflows/{wf_id}/credentials",
        json={"credential_id": cred["id"]},
    )

    deleted = client.delete(f"/api/credentials/{cred['id']}")
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}

    with Session(engine) as session:
        links = session.exec(
            select(WorkflowCredential).where(
                WorkflowCredential.credential_id == cred["id"]
            )
        ).all()
        assert links == []

    listed = client.get(f"/api/workflows/{wf_id}/credentials")
    assert listed.status_code == 200
    assert listed.json() == []


def test_link_and_unlink_touch_workflow_updated_at(client: TestClient) -> None:
    init_db()
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
        before = session.get(Workflow, wf_id)
        assert before is not None
        original_updated = before.updated_at

    cred = _create_cred(client, name=f"touch-{uuid.uuid4().hex[:6]}")
    client.post(
        f"/api/workflows/{wf_id}/credentials",
        json={"credential_id": cred["id"]},
    )

    with Session(engine) as session:
        after_link = session.get(Workflow, wf_id)
        assert after_link is not None
        assert after_link.updated_at >= original_updated

    client.delete(f"/api/workflows/{wf_id}/credentials/{cred['id']}")

    with Session(engine) as session:
        after_unlink = session.get(Workflow, wf_id)
        assert after_unlink is not None
        assert after_unlink.updated_at >= after_link.updated_at


def test_resolve_params_linked_credential_succeeds() -> None:
    init_db()
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
        name = f"linked-{uuid.uuid4().hex[:6]}"
        blob = json.dumps({"username": "alice", "password": "pw"}).encode()
        from app.db.crypto import encrypt

        cred = Credential(name=name, type="generic", ciphertext=encrypt(blob))
        session.add(cred)
        session.commit()
        session.refresh(cred)
        session.add(
            WorkflowCredential(workflow_id=wf_id, credential_id=cred.id)
        )
        session.commit()

        out = resolve_params(
            {"user": f"{{{{cred.{name}.username}}}}"},
            session,
            workflow_id=wf_id,
        )
        assert out["user"] == "alice"


def test_resolve_params_unlinked_credential_rejected() -> None:
    init_db()
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
        other_wf = _seed_workflow(session)
        name = f"unlinked-{uuid.uuid4().hex[:6]}"
        blob = json.dumps({"username": "bob", "password": "pw"}).encode()
        from app.db.crypto import encrypt

        cred = Credential(name=name, type="generic", ciphertext=encrypt(blob))
        session.add(cred)
        session.commit()
        session.refresh(cred)
        session.add(
            WorkflowCredential(workflow_id=other_wf, credential_id=cred.id)
        )
        session.commit()

        with pytest.raises(CredentialResolutionError, match="not linked"):
            resolve_params(
                {"user": f"{{{{cred.{name}.username}}}}"},
                session,
                workflow_id=wf_id,
            )


def test_resolve_params_without_workflow_id_uses_global_namespace() -> None:
    init_db()
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
        name = f"global-{uuid.uuid4().hex[:6]}"
        blob = json.dumps({"username": "carol", "password": "pw"}).encode()
        from app.db.crypto import encrypt

        cred = Credential(name=name, type="generic", ciphertext=encrypt(blob))
        session.add(cred)
        session.commit()
        session.refresh(cred)
        # Deliberately no WorkflowCredential link on wf_id.

        out = resolve_params(
            {"user": f"{{{{cred.{name}.username}}}}"},
            session,
            workflow_id=None,
        )
        assert out["user"] == "carol"


def test_resolve_params_unknown_credential_still_fails() -> None:
    init_db()
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
        with pytest.raises(CredentialResolutionError, match="unknown credential"):
            resolve_params(
                {"x": "{{cred.does_not_exist.field}}"},
                session,
                workflow_id=wf_id,
            )
