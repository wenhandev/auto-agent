"""Tests for pluggable credential backends (local, env, vault, http_vault, stubs)."""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from sqlmodel import Session

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.crypto import encrypt
from app.db.models import Credential, Workflow, WorkflowCredential, WorkflowVersion
from app.db.session import engine, init_db
from app.services.credential_backends import (
    AzureKeyVaultCredentialBackend,
    AzureKeyVaultNotConfiguredError,
    BitwardenCredentialBackend,
    BitwardenNotConfiguredError,
    CredentialNotFoundError,
    EnvCredentialBackend,
    HttpVaultCredentialBackend,
    HttpVaultNotConfiguredError,
    LocalCredentialBackend,
    OnePasswordCredentialBackend,
    OnePasswordNotConfiguredError,
    ReadOnlyBackendError,
    VaultCredentialBackend,
    VaultNotImplementedError,
    create_registry,
)
from app.services.credential_interpolation import (
    CredentialResolutionError,
    resolve_params,
)
from app.services.credential_service import parse_cred_token
from app.settings import settings


@pytest.fixture()
def session() -> Session:
    init_db()
    with Session(engine) as s:
        yield s


def _seed_workflow(session: Session) -> str:
    wf = Workflow(
        name=f"wf-{uuid.uuid4().hex[:8]}",
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


def test_parse_cred_token_plain_name() -> None:
    assert parse_cred_token("github") == (None, "github")


def test_parse_cred_token_namespaced() -> None:
    assert parse_cred_token("env:github") == ("env", "github")


class TestLocalBackend:
    def test_get_returns_decrypted_fields(self, session: Session) -> None:
        name = f"local-{uuid.uuid4().hex[:6]}"
        blob = json.dumps({"username": "alice", "password": "secret"}).encode()
        session.add(Credential(name=name, type="generic", ciphertext=encrypt(blob)))
        session.commit()

        backend = LocalCredentialBackend(session)
        fields = backend.get(name)
        assert fields == {"username": "alice", "password": "secret"}

    def test_get_unknown_raises(self, session: Session) -> None:
        backend = LocalCredentialBackend(session)
        with pytest.raises(CredentialNotFoundError, match="unknown credential"):
            backend.get("missing-cred")

    def test_capabilities_include_write(self, session: Session) -> None:
        backend = LocalCredentialBackend(session)
        assert backend.capabilities.write is True
        assert backend.capabilities.read is True


class TestEnvBackend:
    def test_get_resolves_prefixed_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AUTOAGENT_CRED_GITHUB_PASSWORD", "from-env")
        monkeypatch.setenv("AUTOAGENT_CRED_GITHUB_USERNAME", "bot")

        backend = EnvCredentialBackend()
        assert backend.get("github") == {
            "password": "from-env",
            "username": "bot",
        }

    def test_get_unknown_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AUTOAGENT_CRED_MISSING_TOKEN", raising=False)
        backend = EnvCredentialBackend()
        with pytest.raises(CredentialNotFoundError, match="unknown credential"):
            backend.get("missing")

    def test_put_rejected_as_read_only(self) -> None:
        backend = EnvCredentialBackend()
        with pytest.raises(ReadOnlyBackendError, match="read-only"):
            backend.put("github", {"password": "x"})

    def test_list_refs_discovers_env_credentials(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AUTOAGENT_CRED_GITHUB_PASSWORD", "p")
        monkeypatch.setenv("AUTOAGENT_CRED_STRIPE_KEY", "k")

        backend = EnvCredentialBackend()
        names = {r.name for r in backend.list_refs()}
        assert "github" in names
        assert "stripe" in names


class TestVaultBackend:
    def test_get_raises_not_implemented_by_default(self) -> None:
        backend = VaultCredentialBackend()
        with pytest.raises(VaultNotImplementedError, match="not implemented"):
            backend.get("any")

    def test_mock_fetch_for_tests(self) -> None:
        backend = VaultCredentialBackend(
            fetch=lambda name: {"token": f"vault-{name}"}
        )
        assert backend.get("svc") == {"token": "vault-svc"}


class TestHttpVaultBackend:
    def test_get_raises_when_unconfigured(self) -> None:
        backend = HttpVaultCredentialBackend(url=None, auth_header=None)
        with pytest.raises(HttpVaultNotConfiguredError, match="not configured"):
            backend.get("svc")

    def test_mock_fetch_for_tests(self) -> None:
        backend = HttpVaultCredentialBackend(
            fetch=lambda name: {"token": f"http-{name}"}
        )
        assert backend.get("svc") == {"token": "http-svc"}

    def test_get_via_mock_transport(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("Authorization") == "Bearer test-token"
            assert request.url.path.endswith("/github")
            return httpx.Response(200, json={"password": "from-http-vault"})

        backend = HttpVaultCredentialBackend(
            url="https://vault.example.com/credentials",
            auth_header="Bearer test-token",
            transport=httpx.MockTransport(handler),
        )
        assert backend.get("github") == {"password": "from-http-vault"}

    def test_get_unknown_returns_404(self) -> None:
        transport = httpx.MockTransport(
            lambda r: httpx.Response(404, json={"detail": "missing"})
        )
        backend = HttpVaultCredentialBackend(
            url="https://vault.example.com/credentials",
            transport=transport,
        )
        with pytest.raises(CredentialNotFoundError, match="unknown credential"):
            backend.get("missing")

    def test_put_rejected_as_read_only(self) -> None:
        backend = HttpVaultCredentialBackend(fetch=lambda name: {"x": "y"})
        with pytest.raises(ReadOnlyBackendError, match="read-only"):
            backend.put("svc", {"x": "z"})


class TestExternalBackendStubs:
    @pytest.mark.parametrize(
        ("backend_cls", "error_cls", "mount"),
        [
            (BitwardenCredentialBackend, BitwardenNotConfiguredError, "bitwarden"),
            (OnePasswordCredentialBackend, OnePasswordNotConfiguredError, "onepassword"),
            (
                AzureKeyVaultCredentialBackend,
                AzureKeyVaultNotConfiguredError,
                "azure_key_vault",
            ),
        ],
    )
    def test_get_raises_clear_error(
        self,
        backend_cls: type,
        error_cls: type,
        mount: str,
    ) -> None:
        backend = backend_cls()
        with pytest.raises(error_cls, match="not implemented"):
            backend.get("any")

    def test_registry_routes_http_vault_mount(self, session: Session) -> None:
        registry = create_registry(
            session,
            backends={
                "local": LocalCredentialBackend(session),
                "http_vault": HttpVaultCredentialBackend(
                    fetch=lambda name: {"token": f"hv-{name}"}
                ),
            },
        )
        assert registry.resolve_field("api", "token", mount="http_vault") == "hv-api"

    def test_registry_stub_mount_clear_error(self, session: Session) -> None:
        registry = create_registry(session)
        with pytest.raises(Exception, match="not implemented"):
            registry.resolve_field("github", "password", mount="bitwarden")


class TestRegistryRouting:
    def test_default_mount_from_settings(self, session: Session) -> None:
        registry = create_registry(session, default_mount="local")
        assert registry.default_mount == "local"

    def test_resolve_local_default_mount(self, session: Session) -> None:
        name = f"reg-{uuid.uuid4().hex[:6]}"
        blob = json.dumps({"password": "pw"}).encode()
        session.add(Credential(name=name, type="generic", ciphertext=encrypt(blob)))
        session.commit()

        registry = create_registry(session, default_mount="local")
        assert registry.resolve_field(name, "password") == "pw"

    def test_resolve_env_mount_explicit(self, session: Session, monkeypatch) -> None:
        monkeypatch.setenv("AUTOAGENT_CRED_API_TOKEN", "tok")
        registry = create_registry(session, default_mount="local")
        assert registry.resolve_field("api", "token", mount="env") == "tok"

    def test_per_run_cache_avoids_double_fetch(
        self, session: Session, monkeypatch
    ) -> None:
        name = f"cache-{uuid.uuid4().hex[:6]}"
        blob = json.dumps({"password": "pw"}).encode()
        session.add(Credential(name=name, type="generic", ciphertext=encrypt(blob)))
        session.commit()

        calls = {"n": 0}
        original_get = LocalCredentialBackend.get

        def counting_get(self, cred_name: str) -> dict[str, str]:
            calls["n"] += 1
            return original_get(self, cred_name)

        monkeypatch.setattr(LocalCredentialBackend, "get", counting_get)
        registry = create_registry(session, default_mount="local")
        registry.resolve_field(name, "password")
        registry.resolve_field(name, "password")
        assert calls["n"] == 1

    def test_local_link_enforcement(self, session: Session) -> None:
        wf_id = _seed_workflow(session)
        other_wf = _seed_workflow(session)
        name = f"linked-{uuid.uuid4().hex[:6]}"
        blob = json.dumps({"username": "alice"}).encode()
        cred = Credential(name=name, type="generic", ciphertext=encrypt(blob))
        session.add(cred)
        session.commit()
        session.refresh(cred)
        session.add(WorkflowCredential(workflow_id=other_wf, credential_id=cred.id))
        session.commit()

        registry = create_registry(session, default_mount="local")
        with pytest.raises(Exception, match="not linked"):
            registry.resolve_field(
                name,
                "username",
                workflow_id=wf_id,
                allowed_ids=set(),
            )


class TestInterpolationIntegration:
    def test_unprefixed_token_uses_default_local(self, session: Session) -> None:
        wf_id = _seed_workflow(session)
        name = f"tok-{uuid.uuid4().hex[:6]}"
        blob = json.dumps({"username": "alice", "password": "pw"}).encode()
        cred = Credential(name=name, type="generic", ciphertext=encrypt(blob))
        session.add(cred)
        session.commit()
        session.refresh(cred)
        session.add(WorkflowCredential(workflow_id=wf_id, credential_id=cred.id))
        session.commit()

        out = resolve_params(
            {"user": f"{{{{cred.{name}.username}}}}"},
            session,
            workflow_id=wf_id,
        )
        assert out["user"] == "alice"

    def test_namespaced_env_token(self, session: Session, monkeypatch) -> None:
        monkeypatch.setenv("AUTOAGENT_CRED_GITHUB_PASSWORD", "env-secret")
        out = resolve_params(
            {"pw": "{{cred.env:github.password}}"},
            session,
            workflow_id=None,
        )
        assert out["pw"] == "env-secret"

    def test_namespaced_local_token(self, session: Session) -> None:
        name = f"ns-{uuid.uuid4().hex[:6]}"
        blob = json.dumps({"token": "local-val"}).encode()
        session.add(Credential(name=name, type="generic", ciphertext=encrypt(blob)))
        session.commit()

        out = resolve_params(
            {"t": f"{{{{cred.local:{name}.token}}}}"},
            session,
            workflow_id=None,
        )
        assert out["t"] == "local-val"

    def test_credential_backend_setting_env_default(
        self, session: Session, monkeypatch
    ) -> None:
        monkeypatch.setenv("AUTOAGENT_CRED_APP_PASSWORD", "default-env-pw")
        monkeypatch.setattr(settings, "credential_backend", "env")

        out = resolve_params(
            {"pw": "{{cred.app.password}}"},
            session,
            workflow_id=None,
        )
        assert out["pw"] == "default-env-pw"

    def test_vault_mount_not_implemented(self, session: Session) -> None:
        with pytest.raises(CredentialResolutionError, match="not implemented"):
            resolve_params(
                {"x": "{{cred.vault:svc.token}}"},
                session,
                workflow_id=None,
            )
