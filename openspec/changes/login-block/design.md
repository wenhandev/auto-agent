## Context

`vision-action-mode` gives us a goal-driven agent; `totp-2fa-automation` gives us live 2FA codes; `credential-vault` + `per-workflow-credentials` give us scoped secrets. A `login` node is the composition of these three behind one high-level primitive, with a login-specific prompt and success check. Skyvern's `login` block is exactly this composition.

## Goals / Non-Goals

**Goals:**
- One node that authenticates reliably across varied login forms using vision.
- Seamless 2FA when a TOTP credential is present.
- Skip login entirely when a profile already holds a valid session.

**Non-Goals:**
- OAuth/SSO protocol handling beyond clickable web flows.
- CAPTCHA solving.
- Auto-selecting which credential to use.

## Decisions

### Decision 1: `login` is a scoped `vision_navigate` with a login prompt + injected secrets
The handler builds a vision sub-flow whose system prompt is login-specialised ("find the username/password fields, fill them from the provided credential, submit, handle 2FA if asked"), and injects the username/password/TOTP via tools that return masked placeholders to the model but type real values into the page.
- **Why**: reuse one agent; never put the raw secret in the LLM context. The model says "type the password into field 2"; the tool fills the actual secret.
- **Alternative rejected**: a deterministic selector-based login (breaks on form changes — the very thing we're fixing).

### Decision 2: Secrets never enter the LLM context
The agent sees `<password for my-login>`, not the password. A `fill_credential(index, field)` tool reads the real value server-side and types it.
- **Why**: prevents secret leakage into prompts, traces, and the model provider.

### Decision 3: Success verification is explicit-or-heuristic
If `success_criteria` is given, verify it (URL contains / element present / text present). Otherwise use a default heuristic: the page no longer presents a password field and the URL changed.
- **Why**: avoids false "logged in" on a failed attempt; lets the author tighten the check.

### Decision 4: Profile short-circuit
If the run is profile-seeded and a quick check shows an authenticated state (no login form at the target), `login` emits `login_completed{method:"profile"}` and skips.
- **Why**: the whole point of profiles is to skip login; the node must honour that.

### Decision 5: 2FA retry on rollover
If a filled TOTP code is rejected, the node requests a fresh code once and retries the 2FA submit.
- **Why**: a code typed at the 30s boundary may roll over; one retry covers it.

## Risks / Trade-offs

- [Wrong field filled] → login-specialised prompt + success verification; failure emits `login_failed` with the masked outcome, not a half-authenticated state.
- [Secret leakage] → secrets resolved server-side in tools, never in the model context or traces.
- [CAPTCHA at login] → out of scope; `login_failed` with reason `captcha_suspected`; `captcha-antibot-proxy` handles later.
- [Infinite 2FA loop] → single fresh-code retry, then fail.

## Migration Plan

- Additive `login` node type + `LoginParams`. No DB migration.
- New events `login_started` / `login_completed` / `login_failed` in the literal.

## Open Questions

- Should `login` auto-capture a profile on success (so the next run skips it)? (Lean: emit a suggestion, let the operator click "保存为配置档" — consistent with `browser-sessions-profiles` Decision 5.)
