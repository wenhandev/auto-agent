"""Tests for CAPTCHA detection, proxy config, anti-bot hardening."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.crypto import load_or_create_key
from app.db.models import Run, Workflow, WorkflowVersion
from app.db.session import engine, init_db
from app.services import antibot as antibot_svc
from app.services import browser_pool
from app.services import proxy_config as proxy_svc
from app.services.captcha.detection import CaptchaInfo, detect_captcha
from app.services.captcha.external import ExternalCaptchaSolver
from app.services.captcha.handler import handle_captcha_if_present
from app.services.captcha.solver import CaptchaChallenge
from app.services.perception import Observation, perceive
from app.settings import settings


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _ensure_migrations():
    init_db()
    yield


class _CaptchaPage:
    def __init__(self, html_markers: list[str] | None = None) -> None:
        self.url = "https://example.com/challenge"
        self._markers = html_markers or []

    def locator(self, selector: str) -> Any:
        page = self

        class _Loc:
            async def count(self_inner) -> int:  # noqa: N805
                sel = selector.lower()
                for marker in page._markers:
                    m = marker.lower()
                    if m in sel or sel in m:
                        return 1
                return 0

            @property
            def first(self_inner):  # noqa: N805
                return self_inner

        return _Loc()


@pytest.mark.asyncio
async def test_detect_recaptcha_iframe() -> None:
    page = _CaptchaPage(["iframe", "recaptcha"])
    info = await detect_captcha(page)
    assert info.present is True
    assert info.kind == "recaptcha"


@pytest.mark.asyncio
async def test_detect_hcaptcha_widget() -> None:
    page = _CaptchaPage(["hcaptcha"])
    info = await detect_captcha(page)
    assert info.present is True
    assert info.kind == "hcaptcha"


@pytest.mark.asyncio
async def test_detect_challenge_text() -> None:
    page = _CaptchaPage()
    info = await detect_captcha(page, page_text="Please verify you are human to continue")
    assert info.present is True
    assert info.kind == "unknown"


@pytest.mark.asyncio
async def test_no_captcha_on_clean_page() -> None:
    page = _CaptchaPage()
    info = await detect_captcha(page, page_text="Welcome to our shop")
    assert info.present is False


@pytest.mark.asyncio
async def test_perceive_attaches_captcha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "captcha_detection_enabled", True)

    class _Page:
        url = "https://x.test"

        async def title(self) -> str:
            return "X"

        async def screenshot(self, **_: Any) -> bytes:
            return b"png"

        def locator(self, _: str) -> Any:
            class _L:
                async def inner_text(self) -> str:
                    return "verify you are human"

                async def count(self) -> int:
                    return 0

            return _L()

        @property
        def accessibility(self) -> Any:
            class _A:
                async def snapshot(self) -> dict:
                    return {"role": "WebArea", "name": "", "children": []}

            return _A()

    obs = await perceive(_Page())
    assert obs.captcha is not None
    assert obs.captcha.present is True


def test_mask_proxy_credentials() -> None:
    masked = proxy_svc.mask_proxy_dict(
        {
            "server": "http://user:secret@proxy.example:8080",
            "username": "user",
            "password": "secret",
        }
    )
    assert masked["username"] == "***"
    assert masked["password"] == "***"
    assert "secret" not in masked["server"]


def test_create_proxy_row_encrypts_password() -> None:
    load_or_create_key()
    with Session(engine) as session:
        row = proxy_svc.create_proxy_row(
            name=_unique("test-proxy"),
            server="http://proxy.local:3128",
            username="alice",
            password="s3cret",
            session=session,
        )
        assert row.password_ciphertext is not None
        public = proxy_svc.proxy_row_to_public(row)
        assert public["username"] == "***"
        assert public["has_password"] is True
        pw = proxy_svc.proxy_row_to_playwright(row)
        assert pw["password"] == "s3cret"


@pytest.mark.asyncio
async def test_proxy_passthrough_on_context_create(monkeypatch: pytest.MonkeyPatch) -> None:
    load_or_create_key()
    captured: dict[str, Any] = {}

    class _FakePage:
        is_closed = False

    class _FakeContext:
        async def add_init_script(self, _: str) -> None:
            pass

        async def close(self) -> None:
            pass

        async def new_page(self) -> _FakePage:
            return _FakePage()

    class _FakeBrowser:
        def is_connected(self) -> bool:
            return True

        async def new_context(self, **kwargs) -> _FakeContext:
            captured.update(kwargs)
            return _FakeContext()

    with Session(engine) as session:
        wf = Workflow(name=_unique("proxy-wf"))
        session.add(wf)
        session.commit()
        session.refresh(wf)
        version = WorkflowVersion(
            workflow_id=wf.id,
            version_index=1,
            nodes_json="[]",
            edges_json="[]",
            start_id="s",
            authored_by="test",
        )
        session.add(version)
        session.commit()
        proxy = proxy_svc.create_proxy_row(
            name=_unique("run-proxy"),
            server="http://127.0.0.1:8888",
            username="u",
            password="p",
            session=session,
        )
        run = Run(
            workflow_id=wf.id,
            workflow_version_id=version.id,
            proxy_id=proxy.id,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id

    monkeypatch.setattr(settings, "antibot_stealth", False)
    monkeypatch.setattr(browser_pool, "_browser", _FakeBrowser())
    monkeypatch.setattr(browser_pool, "_playwright", MagicMock())
    browser_pool.reset_for_tests()

    await browser_pool.acquire(run_id)
    assert "proxy" in captured
    assert captured["proxy"]["server"] == "http://127.0.0.1:8888"
    assert captured["proxy"]["username"] == "u"
    await browser_pool.release(run_id)


@pytest.mark.asyncio
async def test_stealth_init_script_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    scripts: list[str] = []

    class _Ctx:
        async def add_init_script(self, script: str) -> None:
            scripts.append(script)

    monkeypatch.setattr(settings, "antibot_stealth", True)
    await antibot_svc.apply_stealth_if_enabled(_Ctx())
    assert scripts
    assert "webdriver" in scripts[0]


@pytest.mark.asyncio
async def test_stealth_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    scripts: list[str] = []

    class _Ctx:
        async def add_init_script(self, script: str) -> None:
            scripts.append(script)

    monkeypatch.setattr(settings, "antibot_stealth", False)
    await antibot_svc.apply_stealth_if_enabled(_Ctx())
    assert scripts == []


@pytest.mark.asyncio
async def test_manual_captcha_pause_and_resume() -> None:
    emitted: list[str] = []

    async def emit(event: str, **_: Any) -> None:
        emitted.append(event)

    page = MagicMock()
    obs = Observation(
        url="https://example.com",
        title="Challenge",
        screenshot_bytes=b"x",
        screenshot_ref="/tmp/cap.png",
        ax_snapshot={},
        captcha=CaptchaInfo(present=True, kind="recaptcha"),
    )

    mock_approval = MagicMock()
    mock_approval.id = "ap-1"
    mock_approval.prompt = "solve captcha"
    mock_approval.inputs_schema = []

    resolved = MagicMock()
    resolved.decision = "approve"
    resolved.decision_inputs = {"captcha_solved": True}

    with patch("app.services.approvals.request", return_value=mock_approval), patch(
        "app.services.approvals.wait", new=AsyncMock(return_value=resolved)
    ), patch("app.services.runs.on_approval_pause", new=AsyncMock()), patch(
        "app.services.runs.on_approval_resume", new=AsyncMock()
    ):
        with Session(engine) as session:
            detected = await handle_captcha_if_present(
                page,
                obs,
                emit=emit,
                session=session,
                run_id="run-1",
                node_id="n1",
            )

    assert detected is True
    assert "captcha_detected" in emitted
    assert "captcha_solved" in emitted


@pytest.mark.asyncio
async def test_external_solver_injects_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "captcha_external_solver_url", "http://solver.test/solve")
    monkeypatch.setattr(settings, "captcha_external_solver_key", "key-1")

    page = MagicMock()
    page.url = "https://example.com"

    class _Loc:
        async def count(self) -> int:
            return 1

        async def get_attribute(self, _: str) -> str:
            return "site-key-abc"

        async def evaluate(self, *_a: Any, **_k: Any) -> None:
            return None

        @property
        def first(self):
            return self

    page.locator = MagicMock(return_value=_Loc())

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"token": "tok-xyz", "cost_hint": "0.002"}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.post = AsyncMock(return_value=mock_resp)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client_cls.return_value = client

        solver = ExternalCaptchaSolver()
        result = await solver.solve(
            CaptchaChallenge(
                page=page,
                info=CaptchaInfo(present=True, kind="recaptcha"),
                screenshot_ref="/tmp/x.png",
                url="https://example.com",
            )
        )

    assert result.success is True
    assert result.token == "tok-xyz"
    assert result.cost_hint == "0.002"


@pytest.mark.asyncio
async def test_external_solver_unsolved_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    emitted: list[str] = []

    async def emit(event: str, **_: Any) -> None:
        emitted.append(event)

    monkeypatch.setattr(settings, "captcha_solver", "external")
    monkeypatch.setattr(settings, "captcha_external_solver_url", None)

    page = MagicMock()
    obs = Observation(
        url="https://example.com",
        title="Challenge",
        screenshot_bytes=b"x",
        screenshot_ref="/tmp/cap.png",
        ax_snapshot={},
        captcha=CaptchaInfo(present=True, kind="turnstile"),
    )

    with Session(engine) as session:
        await handle_captcha_if_present(
            page,
            obs,
            emit=emit,
            session=session,
            run_id="run-2",
            node_id="n2",
        )

    assert "captcha_detected" in emitted
    assert "captcha_unsolved" in emitted


@pytest.mark.asyncio
async def test_builtin_recaptcha_skips_manual_solver(monkeypatch: pytest.MonkeyPatch) -> None:
    emitted: list[tuple[str, dict[str, Any]]] = []

    async def emit(event: str, **kwargs: Any) -> None:
        emitted.append((event, kwargs))

    monkeypatch.setattr(settings, "captcha_builtin_heuristics_enabled", True)

    page = MagicMock()
    obs = Observation(
        url="https://example.com",
        title="Challenge",
        screenshot_bytes=b"x",
        screenshot_ref="/tmp/cap.png",
        ax_snapshot={},
        captcha=CaptchaInfo(present=True, kind="recaptcha"),
    )

    with patch(
        "app.agents.fuzzy._click_recaptcha_in_page",
        new=AsyncMock(
            return_value={"clicked": True, "token_present": True, "checkbox_checked": True}
        ),
    ), patch(
        "app.services.captcha.builtin.detect_captcha",
        new=AsyncMock(return_value=CaptchaInfo(present=False)),
    ):
        with Session(engine) as session:
            detected = await handle_captcha_if_present(
                page,
                obs,
                emit=emit,
                session=session,
                run_id="run-builtin",
                node_id="n-builtin",
            )

    assert detected is True
    events = [e for e, _ in emitted]
    assert "captcha_detected" in events
    assert "captcha_solved" in events
    assert "node_awaiting_approval" not in events
    solved_payload = next(kw for ev, kw in emitted if ev == "captcha_solved")
    assert solved_payload.get("method") == "builtin"


def test_antibot_settings_endpoint(client) -> None:
    resp = client.get("/api/settings/antibot")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "env"
    assert data["editable"] is False
    assert "captcha_detection_enabled" in data
    assert data["captcha_solver"] in ("manual", "external")
    assert "proxy_configured" in data
