## Context

`vision-action-mode`'s perception already captures the screenshot + a11y tree on every step — the right place to also detect a challenge. Playwright's `new_context(proxy=...)` and init scripts give us proxy + fingerprint control. Skyvern bundles CAPTCHA solving, anti-bot, and a proxy network as managed infra; locally we provide the *hooks* and a manual-solve fallback, and we are explicit that the managed network is out of scope.

## Goals / Non-Goals

**Goals:**
- Detect CAPTCHAs and either auto-solve (configured external solver) or pause for a human in the live view.
- Configure a proxy per run/session/profile.
- Best-effort anti-bot context tweaks.

**Non-Goals:**
- A managed/rotating proxy network (Cloud-only).
- A bypass guarantee.
- Audio CAPTCHA / advanced ML fingerprinting.

## Decisions

### Decision 1: Detect in perception, act in executor
Perception flags `captcha: {present, kind}`; the executor decides what to do based on the configured solver.
- **Why**: detection needs the page snapshot perception already has; the policy belongs to the executor.

### Decision 2: Manual solve is the default, via the approval mechanism
With no external solver configured, a detected CAPTCHA pauses the run (reusing `human-in-the-loop`'s pause/resume) and surfaces a banner over the **livestream** so the operator solves it live, then resumes.
- **Why**: a safe, honest default that needs no third-party service; the livestream makes manual solve actually usable.
- **Alternative rejected**: silently failing on CAPTCHA (today's behaviour — unusable).

#### Skyvern-style human handoff on `captcha_detected`

Skyvern Cloud may auto-solve CAPTCHAs; self-hosted and local POC flows rely on **human takeover** when automation cannot clear the challenge. Our equivalent pipeline:

1. **Detect** — perception (or post-navigation scan) flags `captcha: {present, kind}` and emits `captcha_detected` with kind + screenshot artifact.
2. **Try built-in heuristics** (opt-in via `CAPTCHA_BUILTIN_HEURISTICS_ENABLED`, default on) — `click_recaptcha` for reCAPTCHA v2 checkbox; `drag_puzzle` for slider/puzzle widgets. On success, emit `captcha_solved` with `method=builtin` and continue the run without pausing.
3. **External solver** (optional, `captcha_solver=external`) — POST to a configurable HTTP solver, inject token, emit `captcha_solved` or `captcha_unsolved`.
4. **Human handoff** (default fallback, `captcha_solver=manual`) — reuse the approval mechanism:
   - emit `node_awaiting_approval` with `captcha_kind` + `screenshot_ref` and prompt *"CAPTCHA detected. Solve the challenge in the live browser view, then approve to continue."*
   - pause run (`on_approval_pause`); operator solves in the live browser tab
   - operator approves with `captcha_solved=true` → emit `captcha_solved`, resume run
   - reject/abort → emit `captcha_unsolved`, vision/executor may retry or fail

This mirrors Skyvern's "pause for human when solver unavailable" pattern without claiming Cloud-only auto-solve parity.

### Decision 3: External solver behind a strategy interface
`CaptchaSolver.solve(challenge) -> token|None`. The `external` adapter POSTs to a configurable HTTP solver and injects the returned token (`g-recaptcha-response` etc.).
- **Why**: pluggable, vendor-agnostic; mirrors the credential-backend strategy pattern. Keeps any specific vendor SDK optional.

### Decision 4: Proxy is config, not a network
`{server, username?, password?}` per run/session/profile, creds encrypted. Point it at a proxy you operate.
- **Why**: gives the capability without claiming to run a proxy network; honest scope.

### Decision 5: Stealth is opt-in and labelled best-effort
`ANTIBOT_STEALTH` injects an init script masking obvious automation tells; UA/locale/timezone/viewport configurable.
- **Why**: helps with naive bot checks; we do not promise to defeat sophisticated fingerprinting, and we say so.

## Risks / Trade-offs

- [External solver cost/latency/legal] → opt-in, off by default; `cost_hint` emitted; documented that the operator is responsible for ToS compliance.
- [Manual solve stalls a slot] → integrates with `concurrent-runs-browser-pool` slot-release-on-pause.
- [Proxy creds leak] → encrypted at rest; masked in UI/traces.
- [Stealth oversold] → labelled best-effort in UI + docs; no bypass guarantee.

## Migration Plan

- `create_all` makes `proxy`. New settings `ANTIBOT_STEALTH` (default off), default solver `manual`.
- Perception gains the detector; executor gains the solve hook.
- No behaviour change unless a proxy/solver/stealth is configured.

## Open Questions

- Should detection also run on deterministic (non-vision) nodes? (Lean: a lightweight marker scan on navigation completion, independent of vision.)
- Per-domain proxy rules (use proxy X for site Y)? (Defer; per-run/session/profile is enough for v1.)
