## Context

The credential vault stores arbitrary name→fields secrets encrypted with Fernet and resolves `{{cred.<name>.<field>}}` at action time. TOTP and card credentials are just typed shapes over that same store plus, for TOTP, a deterministic code generator (RFC 6238). Skyvern exposes `totp_identifier` on a task so the agent can fetch the rotating code when a 2FA field appears.

## Goals / Non-Goals

**Goals:**
- First-class `totp` and `credit_card` credential kinds with strict field shapes.
- Auto-generate the live TOTP code at action time, no human babysitting.
- Never expose the TOTP secret or full card number on any read path.

**Non-Goals:**
- Non-TOTP 2FA (SMS/email/push/WebAuthn).
- A managed card vault / PCI compliance (this is a local single-user POC; documented caveat).

## Decisions

### Decision 1: TOTP via stdlib, no new dependency
`hmac` + `hashlib` + `struct` + `base64` implement RFC 6238 in ~20 lines. Validated against the RFC test vectors.
- **Why**: avoid pulling `pyotp` for something this small; fewer supply-chain surfaces. (`pyotp` remains a drop-in if we ever want extras.)

### Decision 2: Two resolution paths — token and `totp_identifier`
- `{{totp.<name>}}` for design-time placement in a node's params (deterministic, visible in the graph).
- `totp_identifier` on the run for vision/login flows that decide *at runtime* that a code is needed and call `totp.current_code(identifier)`.
- **Why**: covers both the explicit `fill` node and the autonomous `vision_navigate`/`login` case, matching Skyvern.

### Decision 3: Generate at the current step, document skew
Generation uses the current 30s step; verification skew (±1) is documented for sites with clock drift but not applied to generation (we are the client typing the code, the server validates).
- **Why**: the code we type must match the authenticator's current code; skew handling is the server's job.

### Decision 4: Masking is mandatory and centralised
The masker gains rules: TOTP secret → fully masked; card number → last-4 only; cvc → fully masked. The only place plaintext flows is into the live page fill.
- **Why**: prevents leakage into logs, traces (`run-artifacts-observability`), and API reads.

### Decision 5: Per-workflow link enforcement applies unchanged
`{{totp...}}` / `{{card...}}` resolve only for credentials linked to the run's workflow, identical to `{{cred...}}`.
- **Why**: one security model for all credential token families.

## Risks / Trade-offs

- [Card PAN stored locally] → encrypted at rest + masked reads + explicit "local POC only, not PCI" caveat in docs and the UI create form.
- [TOTP secret entry errors] → "validate now" button shows the current code at create time so the operator can compare with their authenticator app.
- [Code typed just before rollover] → the login/vision flow re-requests a fresh code on a 2FA retry; documented.
- [Token leakage into traces] → mandatory masking pass before any persistence/return.

## Migration Plan

- No DB migration: `kind` is a free-text column; the pydantic layer adds the two enum values and their field schemas.
- New `{{totp...}}` / `{{card...}}` tokens added to the chained resolver.
- `POST /api/runs` gains optional `totp_identifier`.

## Open Questions

- Should `vision_navigate` auto-detect a 2FA field and pull the run's `totp_identifier` without an explicit token? (Lean yes — the agent's tool surface gets a `get_totp()` tool gated on a configured identifier.)
- Card auto-fill heuristics for varied checkout forms — defer field-mapping intelligence to the vision agent.
