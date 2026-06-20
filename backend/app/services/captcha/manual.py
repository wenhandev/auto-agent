"""Manual CAPTCHA solver: pause via approval mechanism for human solve."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Optional

from sqlmodel import Session

from app.services.captcha.solver import (
    CaptchaChallenge,
    CaptchaSolveResult,
    CaptchaSolver,
)


Emit = Callable[..., Awaitable[None]]


class ManualCaptchaSolver(CaptchaSolver):
    def __init__(
        self,
        *,
        emit: Optional[Emit] = None,
        session: Optional[Session] = None,
        run_id: Optional[str] = None,
        node_id: Optional[str] = None,
        abort_event: Optional[asyncio.Event] = None,
    ) -> None:
        self._emit = emit
        self._session = session
        self._run_id = run_id
        self._node_id = node_id or "captcha"
        self._abort_event = abort_event

    async def solve(self, challenge: CaptchaChallenge) -> CaptchaSolveResult:
        if self._emit is None or self._session is None or self._run_id is None:
            return CaptchaSolveResult(
                success=False,
                error="manual solver requires emit, session, and run_id",
            )

        from app.services import approvals as approvals_svc
        from app.services import runs as run_svc

        approval = approvals_svc.request(
            self._session,
            run_id=self._run_id,
            node_id=self._node_id,
            prompt=(
                "CAPTCHA detected. Solve the challenge in the live browser view, "
                "then approve to continue."
            ),
            inputs_schema=[
                {
                    "name": "captcha_solved",
                    "type": "boolean",
                    "required": True,
                    "label": "I have solved the CAPTCHA",
                }
            ],
        )
        await self._emit(
            "node_awaiting_approval",
            node_id=self._node_id,
            prompt=approval.prompt,
            inputs_schema=approval.inputs_schema,
            captcha_kind=challenge.info.kind,
            screenshot_ref=challenge.screenshot_ref,
        )
        await run_svc.on_approval_pause(self._run_id)
        try:
            resolved = await approvals_svc.wait(
                approval.id, abort_event=self._abort_event
            )
        except approvals_svc.ApprovalWaitAborted:
            await run_svc.on_approval_resume(self._run_id)
            return CaptchaSolveResult(success=False, error="aborted")

        await run_svc.on_approval_resume(self._run_id)

        if resolved.decision != "approve":
            return CaptchaSolveResult(success=False, error="rejected")

        inputs = dict(resolved.decision_inputs or {})
        if not inputs.get("captcha_solved"):
            return CaptchaSolveResult(success=False, error="not_confirmed")

        return CaptchaSolveResult(success=True)


__all__ = ["ManualCaptchaSolver"]
