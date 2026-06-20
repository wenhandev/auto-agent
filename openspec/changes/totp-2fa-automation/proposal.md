## depends_on

- `auto-agent-platform` — `credential-vault` (the Fernet store, `Credential` entity, the masker, lookup-by-name interpolation).
- `per-workflow-credentials` (soft) — TOTP/card credentials are linked to workflows the same way other credentials are.

Consumed by `login-block` (which calls the TOTP generator during authentication).

## Why

Most real automations sit behind a login, and most logins now demand a **2FA code**. Today a 2FA prompt is a dead end: the operator must babysit the run and hand-type the code, defeating unattended automation. Skyvern stores the **TOTP secret** as a first-class credential type and **auto-generates + auto-fills** the rotating code during the run; it also stores **credit-card** credentials for checkout flows. This change brings both typed credential kinds and the TOTP generator to `auto-agent`.

## What Changes

- **Credential kinds**: extend the `Credential.kind` enum with `totp` and `credit_card` (the enum already allows `other` for flexibility; these promote the two Skyvern-parity kinds to typed shapes):
  - `totp`: fields `{secret: str (base32), digits?: 6, period?: 30, algorithm?: "SHA1"}`. Stored encrypted; the secret is never returned in plaintext by any read endpoint.
  - `credit_card`: fields `{number, exp_month, exp_year, cvc, holder_name?, zip?}`. All encrypted; reads return masked (`**** **** **** 1234`).
- **TOTP service** `app/services/totp.py`: `current_code(credential_name) -> str` computes the RFC-6238 TOTP for a stored secret using the standard library + `hmac` (no heavy dependency), honouring `digits`/`period`/`algorithm`. A small skew window (±1 step) is documented but generation uses the current step.
- **TOTP interpolation token**: `{{totp.<credential_name>}}` resolves at action time to the current code (resolved in the same interpolation pass as `{{cred...}}`, subject to the same per-workflow link enforcement). This lets a `fill` / `vision_act` node drop the live code into the 2FA input.
- **`totp_identifier` on runs**: `POST /api/runs` accepts an optional `totp_identifier` (a credential name) so a vision/login flow can request the code on demand without hardcoding the token in a node — mirrors Skyvern's `totp_identifier`.
- **Card interpolation**: `{{card.<name>.<field>}}` resolves card fields (number/exp/cvc) at action time, masked everywhere except the actual page fill.
- **UI**: the credentials page gains typed create forms for `totp` (with a "validate now" button showing the current code so the operator can confirm the secret was entered correctly) and `credit_card` (masked). Reads never reveal the secret/number.

## Capabilities

### New Capabilities

- `totp-credentials`: the `totp` credential kind, the RFC-6238 generator service, the `{{totp.<name>}}` token, the `totp_identifier` run option, and the credential UI (with validate-now).
- `card-credentials`: the `credit_card` credential kind, the `{{card.<name>.<field>}}` token, masked reads, and the credential UI.

### Modified Capabilities

- `credential-vault` (from `auto-agent-platform`): `Credential.kind` gains `totp` and `credit_card` with typed field shapes; the masker learns the card-number and secret masking rules; the interpolation pass learns the `{{totp...}}` and `{{card...}}` token families.
- `node-output-interpolation` / credential interpolation: the chained resolver adds the two token families; per-workflow link enforcement applies identically.

## Impact

- **Backend**: new `app/services/totp.py` (pure stdlib `hmac`/`hashlib`/`struct`/`base64`). Extend the credential field schema + masker. Extend the interpolation resolver with two token families. `POST /api/runs` gains `totp_identifier`. Tests: TOTP test-vectors (RFC 6238), masking, link enforcement on the new tokens.
- **Frontend**: typed credential create forms + validate-now; masked displays.
- **Runtime**: TOTP generation is microseconds; no LLM, no network.
- **Migration**: no new table; `kind` is free-text in the column with a pydantic enum at the schema layer (same pattern `human-in-the-loop` used for run status), so adding kinds needs no DB migration. Existing credentials keep their `kind`.
- **Out of scope**: SMS/email OTP retrieval (requires an inbox integration — future `otp-inbox` change); push-approval 2FA (Duo/Okta Verify); hardware keys / WebAuthn; storing full card PANs for anything beyond local single-user POC use (documented security caveat).
