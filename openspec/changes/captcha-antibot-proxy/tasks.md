## 1. Detection

- [x] 1.1 Add CAPTCHA marker detection to the perception layer (reCAPTCHA/hCaptcha/Turnstile + challenge text)
- [x] 1.2 Emit `captcha_detected` with kind + screenshot artifact; add to event literal
- [x] 1.3 Optional lightweight detection on navigation completion (non-vision nodes)

## 2. Solver strategy

- [x] 2.1 Create `app/services/captcha/` with a `CaptchaSolver` interface
- [x] 2.2 `manual` adapter pausing via the approval mechanism + livestream banner
- [x] 2.3 `external` adapter (HTTP solver, token injection) with encrypted creds
- [x] 2.4 Emit `captcha_solved` / `captcha_unsolved`
- [x] 2.5 Executor invokes the configured solver on `captcha_detected`
- [x] 2.6 Built-in heuristics (`click_recaptcha`, `drag_puzzle`) before manual/external fallback

## 3. Proxy

- [x] 3.1 `Proxy` config table (encrypted creds) + default-proxy setting
- [x] 3.2 Pass `proxy=...` into context creation per run/session/profile
- [x] 3.3 Mask proxy creds in UI/traces

## 4. Anti-bot hardening

- [x] 4.1 Configurable user agent / locale / timezone / viewport on context creation
- [x] 4.2 `ANTIBOT_STEALTH` init-script toggle (mask `navigator.webdriver` etc.)

## 5. Frontend

- [ ] 5.1 Settings "反爬与代理" section (solver + proxy + stealth)
- [ ] 5.2 Run-view CAPTCHA banner over the livestream for manual solve

## 6. Tests

- [x] 6.1 Detection on fixture challenge pages
- [x] 6.2 Manual-solve pause/resume; external-solver token injection (faked)
- [x] 6.3 Proxy passthrough; cred masking
- [x] 6.4 Stealth toggle effect on `navigator.webdriver`
