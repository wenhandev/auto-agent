"""Orchestrate CAPTCHA detection events and solver invocation."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Optional

from playwright.async_api import Page
from sqlmodel import Session

from app.services import artifact_context
from app.services.captcha.detection import CaptchaInfo
from app.services.captcha.manual import ManualCaptchaSolver
from app.services.captcha.solver import CaptchaChallenge, get_solver
from app.settings import settings


Emit = Callable[..., Awaitable[None]]


async def emit_captcha_detected(
    emit: Emit,
    *,
    info: CaptchaInfo,
    screenshot_ref: str,
    node_id: Optional[str] = None,
) -> None:
    await emit(
        "captcha_detected",
        node_id=node_id or artifact_context.get_node_id(),
        kind=info.kind,
        screenshot_ref=screenshot_ref,
        captcha=info.to_dict(),
    )


async def handle_captcha_if_present(
    page: Page,
    observation: Any,
    *,
    emit: Optional[Emit] = None,
    session: Optional[Session] = None,
    run_id: Optional[str] = None,
    node_id: Optional[str] = None,
    abort_event: Optional[asyncio.Event] = None,
) -> bool:
    """If observation has CAPTCHA, emit event and invoke configured solver.

    Returns True when a CAPTCHA was detected (regardless of solve outcome).
    """
    if not settings.captcha_detection_enabled:
        return False
    if observation.captcha is None or not observation.captcha.present:
        return False

    rid = run_id or artifact_context.get_run_id()
    nid = node_id or artifact_context.get_node_id()
    screenshot_ref = observation.screenshot_ref
    captcha_info = observation.captcha
    obs_url = observation.url

    if emit is not None:
        await emit_captcha_detected(
            emit,
            info=captcha_info,
            screenshot_ref=screenshot_ref,
            node_id=nid,
        )

    if settings.captcha_builtin_heuristics_enabled:
        from app.services.captcha.builtin import try_builtin_solve

        challenge = CaptchaChallenge(
            page=page,
            info=captcha_info,
            screenshot_ref=screenshot_ref,
            url=obs_url,
        )
        builtin_result = await try_builtin_solve(challenge)
        if builtin_result is not None and builtin_result.success:
            if emit is not None:
                payload: dict[str, Any] = {
                    "node_id": nid,
                    "kind": captcha_info.kind,
                    "method": "builtin",
                }
                if builtin_result.cost_hint:
                    payload["cost_hint"] = builtin_result.cost_hint
                await emit("captcha_solved", **payload)
            return True

    solver = get_solver()
    if isinstance(solver, ManualCaptchaSolver):
        solver = ManualCaptchaSolver(
            emit=emit,
            session=session,
            run_id=rid,
            node_id=nid,
            abort_event=abort_event,
        )

    challenge = CaptchaChallenge(
        page=page,
        info=captcha_info,
        screenshot_ref=screenshot_ref,
        url=obs_url,
    )
    result = await solver.solve(challenge)

    if emit is not None:
        if result.success:
            payload: dict[str, Any] = {
                "event": "captcha_solved",
                "node_id": nid,
                "kind": captcha_info.kind,
            }
            if result.cost_hint:
                payload["cost_hint"] = result.cost_hint
            await emit("captcha_solved", **{k: v for k, v in payload.items() if k != "event"})
        else:
            await emit(
                "captcha_unsolved",
                node_id=nid,
                kind=captcha_info.kind,
                error=result.error,
            )

    return True


async def check_navigation_captcha(
    page: Page,
    *,
    emit: Optional[Emit] = None,
    session: Optional[Session] = None,
    run_id: Optional[str] = None,
    node_id: Optional[str] = None,
    abort_event: Optional[asyncio.Event] = None,
) -> bool:
    """Lightweight CAPTCHA scan after navigation (non-vision nodes)."""
    if not settings.captcha_detection_enabled:
        return False
    from app.services.captcha.detection import detect_captcha_lightweight
    from app.services.perception import perceive

    info = await detect_captcha_lightweight(page)
    if not info.present:
        return False

    obs = await perceive(page, ref_hint="nav-captcha")
    obs.captcha = info
    return await handle_captcha_if_present(
        page,
        obs,
        emit=emit,
        session=session,
        run_id=run_id,
        node_id=node_id,
        abort_event=abort_event,
    )


__all__ = [
    "check_navigation_captcha",
    "emit_captcha_detected",
    "handle_captcha_if_present",
]
