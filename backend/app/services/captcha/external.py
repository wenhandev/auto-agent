"""External HTTP CAPTCHA solver adapter with token injection."""

from __future__ import annotations

import logging

import httpx

from app.services.captcha.solver import CaptchaChallenge, CaptchaSolveResult, CaptchaSolver
from app.settings import settings


logger = logging.getLogger(__name__)

_TOKEN_SELECTORS = (
    "textarea#g-recaptcha-response",
    "textarea[name='g-recaptcha-response']",
    "textarea[name='h-captcha-response']",
    "input[name='cf-turnstile-response']",
)


class ExternalCaptchaSolver(CaptchaSolver):
    async def solve(self, challenge: CaptchaChallenge) -> CaptchaSolveResult:
        url = settings.captcha_external_solver_url
        if not url:
            return CaptchaSolveResult(
                success=False, error="captcha_external_solver_url not configured"
            )

        payload = {
            "url": challenge.url,
            "kind": challenge.info.kind,
            "site_key": await self._extract_site_key(challenge.page),
        }
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if settings.captcha_external_solver_key:
            headers["Authorization"] = f"Bearer {settings.captcha_external_solver_key}"

        try:
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("external captcha solver failed: %s", exc)
            return CaptchaSolveResult(success=False, error=str(exc))

        token = data.get("token") or data.get("solution")
        if not token:
            return CaptchaSolveResult(success=False, error="solver returned no token")

        injected = await self._inject_token(challenge.page, str(token))
        if not injected:
            return CaptchaSolveResult(
                success=False, error="token injection failed", token=str(token)
            )

        cost_hint = data.get("cost_hint") or data.get("cost")
        return CaptchaSolveResult(
            success=True, token=str(token), cost_hint=str(cost_hint) if cost_hint else None
        )

    async def _extract_site_key(self, page) -> str | None:
        for sel in ("[data-sitekey]", ".g-recaptcha", ".h-captcha", ".cf-turnstile"):
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    key = await loc.get_attribute("data-sitekey")
                    if key:
                        return key
            except Exception:
                continue
        return None

    async def _inject_token(self, page, token: str) -> bool:
        for sel in _TOKEN_SELECTORS:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    await loc.evaluate(
                        "(el, value) => { el.value = value; el.dispatchEvent(new Event('input', { bubbles: true })); }",
                        token,
                    )
                    return True
            except Exception:
                continue
        try:
            await page.evaluate(
                """(token) => {
                  const names = ['g-recaptcha-response', 'h-captcha-response', 'cf-turnstile-response'];
                  for (const name of names) {
                    let el = document.querySelector(`textarea[name="${name}"]`) ||
                             document.querySelector(`input[name="${name}"]`);
                    if (el) { el.value = token; return true; }
                  }
                  return false;
                }""",
                token,
            )
            return True
        except Exception:
            return False


__all__ = ["ExternalCaptchaSolver"]
