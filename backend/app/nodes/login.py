"""Login node: vision-driven authentication with linked credentials."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional

from sqlmodel import Session, select

from app.agents.login import LoginAgent
from app.db.crypto import decrypt
from app.db.models import Credential, WorkflowCredential
from app.schemas import LoginParams
from app.services.credential_interpolation import CredentialResolutionError
from app.tools import browser as browser_tools
from app.tools.browser import get_page


logger = logging.getLogger(__name__)

Emit = Callable[..., Awaitable[None]]


class LoginError(ValueError):
    pass


_OTP_SELECTORS = (
    "input[autocomplete='one-time-code']",
    "input[name*='otp' i]",
    "input[name*='totp' i]",
    "input[name*='2fa' i]",
    "input[id*='otp' i]",
    "input[type='tel'][maxlength='6']",
    "input[type='text'][maxlength='6']",
)


def _linked_credential_ids(workflow_id: str, session: Session) -> set[str]:
    rows = session.exec(
        select(WorkflowCredential.credential_id).where(
            WorkflowCredential.workflow_id == workflow_id
        )
    ).all()
    return {r for r in rows}


def _load_linked_credential(
    name: str,
    session: Session,
    *,
    workflow_id: Optional[str],
) -> dict[str, str]:
    cred = session.exec(select(Credential).where(Credential.name == name)).first()
    if cred is None:
        raise CredentialResolutionError(f"unknown credential {name!r}")
    if workflow_id is not None:
        allowed = _linked_credential_ids(workflow_id, session)
        if cred.id not in allowed:
            raise CredentialResolutionError(
                f"credential {name!r} is not linked to this workflow; "
                f"open the workflow's '凭证' panel and add it before running"
            )
    try:
        plaintext = decrypt(cred.ciphertext)
        data = __import__("json").loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise CredentialResolutionError(
            f"credential {name!r}: decryption failed"
        ) from exc
    if not isinstance(data, dict):
        raise CredentialResolutionError(f"credential {name!r}: invalid stored blob")
    return {str(k): str(v) for k, v in data.items()}


async def has_password_field(page: Any) -> bool:
    try:
        return await page.locator("input[type='password']").count() > 0
    except Exception:
        return False


async def fill_otp_code(page: Any, code: str) -> bool:
    """Best-effort fill of a visible OTP/2FA input."""
    for sel in _OTP_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                await loc.fill(code)
                return True
        except Exception:
            continue
    return False


async def verify_login_success(
    page: Any,
    *,
    success_criteria: Optional[str],
    start_url: str,
) -> tuple[bool, str]:
    """Explicit criteria or default no-password-field + URL-changed heuristic."""
    if success_criteria:
        crit = success_criteria.strip()
        if crit.startswith("url:"):
            needle = crit[4:].strip()
            if needle and needle in page.url:
                return True, "success_criteria_url"
            return False, "success_criteria_url_mismatch"
        if crit.startswith("selector:"):
            sel = crit[9:].strip()
            try:
                if sel and await page.locator(sel).count() > 0:
                    return True, "success_criteria_selector"
            except Exception:
                pass
            return False, "success_criteria_selector_missing"
        if crit.startswith("text:"):
            needle = crit[5:].strip()
            try:
                body = await page.locator("body").inner_text()
                if needle and needle in body:
                    return True, "success_criteria_text"
            except Exception:
                pass
            return False, "success_criteria_text_missing"
        if await has_password_field(page):
            return False, "password_field_still_present"
        if page.url != start_url:
            return True, "default_heuristic"
        return False, "url_unchanged"

    if await has_password_field(page):
        return False, "password_field_still_present"
    if page.url == start_url:
        return False, "url_unchanged"
    return True, "default_heuristic"


async def _profile_short_circuit(
    url: Optional[str],
) -> Optional[dict[str, Any]]:
    profile_id = browser_tools.get_active_profile_id()
    if not profile_id:
        return None
    page = await get_page()
    if url:
        await page.goto(url)
    if await has_password_field(page):
        return None
    return {
        "logged_in": True,
        "method": "profile",
        "steps": 0,
        "final_url": page.url,
    }


async def _manual_totp_fallback(
    *,
    page: Any,
    node_id: str,
    emit: Emit,
    session: Session,
    run_id: str,
    abort_event: Any = None,
) -> Optional[str]:
    from app.services import approvals as approvals_svc

    approval = approvals_svc.request(
        session,
        run_id=run_id,
        node_id=node_id,
        prompt="Auto-TOTP failed. Enter the 2FA code manually.",
        inputs_schema=[
            {
                "name": "totp_code",
                "type": "string",
                "required": True,
                "label": "2FA code",
            }
        ],
    )
    await emit(
        "node_awaiting_approval",
        node_id=node_id,
        prompt=approval.prompt,
        inputs_schema=approval.inputs_schema,
    )
    await emit(
        "approval_requested",
        node_id=node_id,
        prompt=approval.prompt,
        inputs_schema=approval.inputs_schema,
    )
    try:
        resolved = await approvals_svc.wait(approval.id, abort_event=abort_event)
    except approvals_svc.ApprovalWaitAborted:
        return None
    if resolved is None:
        return None
    if resolved.decision != "approve":
        return None
    inputs = resolved.inputs or {}
    code = str(inputs.get("totp_code") or "").strip()
    if not code:
        return None
    filled = await fill_otp_code(page, code)
    if not filled:
        return None
    await emit(
        "totp_manual_fallback",
        node_id=node_id,
        method="approval",
        masked_code="<totp_code>",
    )
    return code


async def run(
    params: dict[str, Any],
    *,
    node_id: str,
    emit: Emit,
    session: Optional[Session] = None,
    workflow_id: Optional[str] = None,
    run_id: Optional[str] = None,
    abort_event: Any = None,
    totp_identifier: Optional[str] = None,
) -> dict[str, Any]:
    login_params = LoginParams.model_validate(params)
    credential_name = login_params.credential
    totp_id = login_params.totp_identifier or totp_identifier

    if session is None:
        raise LoginError("login node requires a database session")

    await emit(
        "login_started",
        node_id=node_id,
        credential=credential_name,
        url=login_params.url,
    )

    try:
        cred_fields = _load_linked_credential(
            credential_name, session, workflow_id=workflow_id
        )
    except CredentialResolutionError as exc:
        await emit(
            "login_failed",
            node_id=node_id,
            logged_in=False,
            reason=str(exc),
            credential=credential_name,
        )
        raise LoginError(str(exc)) from exc

    short = await _profile_short_circuit(login_params.url)
    if short is not None:
        await emit(
            "login_completed",
            node_id=node_id,
            logged_in=True,
            method="profile",
            steps=0,
            final_url=short["final_url"],
            credential=credential_name,
        )
        return short

    page = await get_page()
    start_url = page.url
    if login_params.url:
        await page.goto(login_params.url)
        start_url = page.url

    async def on_vision_step(step: dict) -> None:
        await emit("vision_step", node_id=node_id, **step)

    async def on_progress(msg: str) -> None:
        await emit("node_progress", node_id=node_id, message=msg)

    agent = LoginAgent()
    flow = await agent.run_login(
        credential_name=credential_name,
        credential_fields=cred_fields,
        session=session,
        workflow_id=workflow_id,
        totp_identifier=totp_id,
        success_criteria=login_params.success_criteria,
        on_step=on_vision_step,
        on_progress=on_progress,
    )

    steps = int(flow.get("steps") or 0)
    final_url = page.url
    agent_summary = str((flow.get("agent_summary") or "")).lower()

    if (
        not flow.get("completed")
        and agent_summary == "2fa_required"
        and login_params.totp_fallback_approval
        and run_id
    ):
        manual = await _manual_totp_fallback(
            page=page,
            node_id=node_id,
            emit=emit,
            session=session,
            run_id=run_id,
            abort_event=abort_event,
        )
        if manual:
            steps += 1
            flow = {"completed": True, "summary": "manual 2fa", "steps": steps}

    ok, verify_reason = await verify_login_success(
        page,
        success_criteria=login_params.success_criteria,
        start_url=start_url,
    )

    if flow.get("completed") and ok:
        outcome = {
            "logged_in": True,
            "method": "vision",
            "steps": steps,
            "final_url": final_url,
        }
        await emit(
            "login_completed",
            node_id=node_id,
            credential=credential_name,
            **outcome,
        )
        return outcome

    reason = verify_reason
    if not flow.get("completed"):
        reason = str(flow.get("reason") or flow.get("agent_summary") or reason)
    await emit(
        "login_failed",
        node_id=node_id,
        logged_in=False,
        method="vision",
        steps=steps,
        final_url=final_url,
        reason=reason,
        credential=credential_name,
    )
    raise LoginError(f"login failed: {reason}")


__all__ = [
    "LoginError",
    "fill_otp_code",
    "has_password_field",
    "run",
    "verify_login_success",
]
