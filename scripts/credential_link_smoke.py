"""Smoke test for the per-workflow-credentials change.

Walks through the full link lifecycle against a running backend on
$AUTO_AGENT_PORT (default 8001), then drops into the backend process
to exercise ``resolve_params`` directly so the interpolation security
check (linked vs unlinked) is verified end-to-end.

Run with the backend already up:

    python scripts/credential_link_smoke.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import httpx


try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


PORT = os.environ.get("AUTO_AGENT_PORT", "8001")
BASE = f"http://127.0.0.1:{PORT}"

PASS = "[PASS]"
FAIL = "[FAIL]"


def _bail(msg: str) -> None:
    print(f"{FAIL} {msg}", flush=True)
    raise SystemExit(1)


def _ok(msg: str) -> None:
    print(f"{PASS} {msg}", flush=True)


def _safe_delete_credential_by_name(client: httpx.Client, name: str) -> None:
    rows = client.get("/api/credentials").json()
    for r in rows:
        if r.get("name") == name:
            client.delete(f"/api/credentials/{r['id']}")


def _run_interpolation_checks(linked_wf_id: str, other_wf_id: str, cred_name: str) -> None:
    """Exercise ``resolve_params`` directly inside the backend's process
    space. Requires this script to run from the same venv as the backend
    (which is how the spec asks us to verify)."""
    backend_root = Path(__file__).resolve().parents[1] / "backend"
    sys.path.insert(0, str(backend_root))
    os.chdir(backend_root)

    from sqlmodel import Session

    from app.db.session import engine
    from app.services.credential_interpolation import (
        CredentialResolutionError,
        resolve_params,
    )

    params = {"instruction": f"user is {{{{cred.{cred_name}.username}}}}"}

    with Session(engine) as session:
        resolved = resolve_params(params, session, workflow_id=linked_wf_id)
    if not isinstance(resolved, dict) or "smoke-user-A" not in resolved["instruction"]:
        _bail(
            f"linked resolve_params did not substitute correctly; got {resolved!r}"
        )
    _ok(
        f"step 7 resolve_params(linked) -> {resolved['instruction']!r}"
    )

    raised: CredentialResolutionError | None = None
    with Session(engine) as session:
        try:
            resolve_params(params, session, workflow_id=other_wf_id)
        except CredentialResolutionError as exc:
            raised = exc
    if raised is None:
        _bail("unlinked resolve_params did NOT raise (security regression)")
    if "not linked" not in str(raised):
        _bail(
            f"unlinked error message missing 'not linked' substring: {raised!s}"
        )
    _ok(f"step 8 resolve_params(unlinked) raised: {raised}")

    raised2: CredentialResolutionError | None = None
    with Session(engine) as session:
        try:
            resolve_params(
                {"x": "{{cred.totally_unknown.field}}"},
                session,
                workflow_id=linked_wf_id,
            )
        except CredentialResolutionError as exc:
            raised2 = exc
    if raised2 is None or "unknown credential" not in str(raised2):
        _bail(
            f"unknown credential should still raise the legacy message; got {raised2!r}"
        )
    _ok(f"step 9 resolve_params(unknown) raised: {raised2}")


def main() -> int:
    timeout = httpx.Timeout(15.0, connect=5.0)
    with httpx.Client(base_url=BASE, timeout=timeout, trust_env=False) as client:
        for _ in range(40):
            try:
                r = client.get("/api/health")
                if r.status_code == 200:
                    break
            except Exception:
                pass
            import time as _time

            _time.sleep(0.25)
        else:
            _bail("backend never became healthy")
        _ok("backend healthy")

        for name in ("smoke-a", "smoke-b"):
            _safe_delete_credential_by_name(client, name)

        r = client.post(
            "/api/credentials",
            json={
                "name": "smoke-a",
                "description": "smoke credential A",
                "fields": {"username": "smoke-user-A", "password": "pwA"},
            },
        )
        if r.status_code != 200:
            _bail(f"create a: HTTP {r.status_code} {r.text!r}")
        cred_a = r.json()

        r = client.post(
            "/api/credentials",
            json={
                "name": "smoke-b",
                "description": "smoke credential B",
                "fields": {"api_key": "kB"},
            },
        )
        if r.status_code != 200:
            _bail(f"create b: HTTP {r.status_code} {r.text!r}")
        cred_b = r.json()
        _ok(
            f"step 1 created creds a={cred_a['id'][:8]} b={cred_b['id'][:8]}"
        )

        rows = client.get("/api/credentials").json()
        by_id = {r["id"]: r for r in rows}
        if by_id.get(cred_a["id"], {}).get("usage_count") != 0:
            _bail(f"a.usage_count not 0 initially: {by_id.get(cred_a['id'])}")
        if by_id.get(cred_b["id"], {}).get("usage_count") != 0:
            _bail(f"b.usage_count not 0 initially: {by_id.get(cred_b['id'])}")
        _ok("step 2 both creds have usage_count == 0")

        workflows = client.get("/api/workflows").json()
        seeded = [w for w in workflows if w["name"] == "示例工作流"]
        if not seeded:
            _bail(
                f"seeded sample workflow missing; got names={[w['name'] for w in workflows]}"
            )
        wf_id = seeded[0]["id"]

        r = client.post(
            "/api/workflows", json={"name": "smoke-other", "description": "second wf"}
        )
        if r.status_code != 200:
            _bail(f"create second workflow: HTTP {r.status_code} {r.text!r}")
        other_wf_id = r.json()["id"]
        _ok(
            f"step 3 seeded wf_id={wf_id[:8]}, second wf_id={other_wf_id[:8]}"
        )

        r = client.post(
            f"/api/workflows/{wf_id}/credentials",
            json={"credential_id": cred_a["id"]},
        )
        if r.status_code != 200:
            _bail(f"link a: HTTP {r.status_code} {r.text!r}")
        linked_item = r.json()
        if linked_item.get("name") != "smoke-a":
            _bail(f"link response unexpected: {linked_item}")
        _ok(f"step 4 linked a to seeded workflow")

        r = client.post(
            f"/api/workflows/{wf_id}/credentials",
            json={"credential_id": cred_a["id"]},
        )
        if r.status_code != 409:
            _bail(f"duplicate link should be 409; got {r.status_code} {r.text!r}")
        _ok("step 5 duplicate link returned 409")

        r = client.get(f"/api/workflows/{wf_id}/credentials")
        if r.status_code != 200:
            _bail(f"list linked: HTTP {r.status_code} {r.text!r}")
        linked = r.json()
        if len(linked) != 1 or linked[0]["id"] != cred_a["id"]:
            _bail(f"linked list should be [a]; got {linked}")
        _ok(f"step 6a workflow link list = [{linked[0]['name']}]")

        rows = client.get("/api/credentials").json()
        by_id = {r["id"]: r for r in rows}
        if by_id[cred_a["id"]]["usage_count"] != 1:
            _bail(f"a.usage_count should be 1; got {by_id[cred_a['id']]}")
        if by_id[cred_b["id"]]["usage_count"] != 0:
            _bail(f"b.usage_count should be 0; got {by_id[cred_b['id']]}")
        _ok("step 6b usage_count a=1 b=0")

        _run_interpolation_checks(wf_id, other_wf_id, "smoke-a")

        r = client.delete(
            f"/api/workflows/{wf_id}/credentials/{cred_a['id']}"
        )
        if r.status_code != 204:
            _bail(f"unlink: HTTP {r.status_code} {r.text!r}")
        _ok("step 10 unlink returned 204")

        rows = client.get("/api/credentials").json()
        by_id = {r["id"]: r for r in rows}
        if by_id[cred_a["id"]]["usage_count"] != 0:
            _bail(f"a.usage_count back to 0; got {by_id[cred_a['id']]}")
        _ok("step 11 a.usage_count back to 0 after unlink")

        client.delete(f"/api/workflows/{other_wf_id}")
        for cid in (cred_a["id"], cred_b["id"]):
            client.delete(f"/api/credentials/{cid}")

    print(f"\n{PASS} per-workflow-credentials smoke complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
