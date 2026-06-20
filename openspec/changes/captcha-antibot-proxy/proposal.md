## depends_on

- `auto-agent-mvp` — the executor, the Chromium launch, the action set.
- `vision-action-mode` — perception is how a CAPTCHA is *detected* on the page.
- `browser-sessions-profiles` (soft) — a proxy/fingerprint is most useful pinned to a session/profile.
- `human-in-the-loop` (soft) — the fallback when no solver is configured is a human-solve pause.

No hard dependency on other in-flight changes.

## Why

Real sites fight bots: CAPTCHAs, rate-limiting, IP reputation, fingerprinting. `auto-agent` has none of these defences, so it fails the moment a site challenges it. Skyvern ships "**CAPTCHA solving, anti-bot bypass, proxy network**" as its reliability layer. We add the *hooks* for this — CAPTCHA detection + a pluggable solver, proxy configuration, and basic anti-bot hardening — while staying honest that a managed proxy network is Cloud-only and out of a local POC's scope.

## What Changes

- **CAPTCHA detection**: the perception layer flags likely CAPTCHA challenges (reCAPTCHA/hCaptcha/Turnstile iframes, common challenge text/markers) and emits a `captcha_detected` event with the kind + screenshot artifact.
- **Pluggable solver**: a `CaptchaSolver` strategy interface with adapters: `manual` (default — pauses via the `human-in-the-loop` approval mechanism so a person solves it in the live view), and `external` (a configurable HTTP solver service, e.g. a 2captcha-style API, with the token injected back). Solver choice + credentials live in Settings (encrypted).
- **Proxy configuration**: per-run / per-session / per-profile proxy settings `{server, username?, password?}` passed to `browser.new_context(proxy=...)`. A `Proxy` config table (encrypted creds) + a default proxy in Settings. No managed proxy *network* — just the config to point at one you own.
- **Anti-bot hardening (best-effort)**: optional context tweaks — realistic `user_agent`, `locale`/`timezone_id`, `viewport`, and a documented `stealth`-style init script toggle (`ANTIBOT_STEALTH`) that masks the most obvious `navigator.webdriver` tells. Explicitly best-effort, not a bypass guarantee.
- **Events/UI**: `captcha_detected` / `captcha_solved` / `captcha_unsolved` events; the run view surfaces a CAPTCHA banner (with the live stream) when a manual solve is needed; Settings gets a "反爬与代理" section (solver + proxy + stealth toggle).

## Capabilities

### New Capabilities

- `captcha-handling`: CAPTCHA detection in perception, the `CaptchaSolver` strategy with `manual` + `external` adapters, the captcha events, and the run-view solve banner.
- `proxy-configuration`: per-run/session/profile proxy settings, the `Proxy` config table with encrypted creds, and the Settings proxy surface.
- `antibot-hardening`: best-effort context fingerprint tweaks + the optional stealth init-script toggle.

### Modified Capabilities

- `vision-perception` (from `vision-action-mode`): perception additionally classifies CAPTCHA presence and kind.
- `hybrid-executor` (from `auto-agent-mvp`): on `captcha_detected`, the executor invokes the configured solver (or pauses for manual solve) before continuing.
- `browser-sessions-profiles` (from `browser-sessions-profiles`): a session/profile may carry a pinned proxy + fingerprint.
- `runtime-llm-config` / Settings: gains solver + proxy + stealth configuration.

## Impact

- **Backend**: detection in perception (~40 LOC), a `app/services/captcha/` strategy package (~150 LOC), proxy plumbing into context creation, a `proxy` config table, init-script injection. New optional dependency only if a specific solver SDK is chosen (the `external` adapter is plain HTTP). Tests: detection on fixture challenge pages, manual-solve pause/resume, external-solver token injection (faked), proxy passthrough, stealth toggle effect on `navigator.webdriver`.
- **Frontend**: Settings "反爬与代理" section; run-view CAPTCHA banner over the live stream.
- **Runtime**: detection is cheap (marker scan); a solve adds latency (human or solver round-trip); proxy adds network hops.
- **Migration**: `create_all` makes `proxy`; new settings `ANTIBOT_STEALTH`, default solver `manual`. No behaviour change unless configured.
- **Out of scope**: a managed/rotating proxy network (Cloud-only — explicitly out of the local POC, mirroring `SKYVERN_PARITY.md` §4); guaranteed anti-bot bypass; audio-CAPTCHA solving; ML-based fingerprint randomisation beyond the documented basic tweaks.
