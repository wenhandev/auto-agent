## depends_on

- `auto-agent-mvp` — workflow schema, executor dispatch, action set.
- `vision-action-mode` — the vision agent + perception layer drive the actual form-finding and filling.
- `totp-2fa-automation` — the `login` block requests the live 2FA code when a 2FA step appears.
- `per-workflow-credentials` — the login block references a linked credential.

No dependency on other in-flight changes.

## Why

Logging in is the single most common precondition for real automation, and it is fiddly: find the username field, the password field, submit, handle a possible 2FA prompt, confirm success. Skyvern ships a dedicated **`login` block** that does exactly this with a stored credential. Without it, every workflow re-implements login as a brittle sequence of `fill`/`click` nodes that breaks the moment the form changes.

This change adds a single high-level `login` node: point it at a credential, and it authenticates — using vision to locate fields, the credential vault for username/password, and the TOTP service for 2FA.

## What Changes

- **New node type** `login` on the `NodeType` literal. Params: `{credential: str, url?: str, success_criteria?: str, totp_identifier?: str}`.
- **Behaviour**: the executor runs a scoped vision sub-flow: (optionally navigate to `url`) → locate and fill the username/password from the linked credential → submit → IF a 2FA field appears AND a TOTP credential is available THEN generate + fill the code → verify against `success_criteria` (or a default "no longer on a login form" heuristic). Output: `{logged_in: bool, method, steps, final_url}`.
- **Credential coupling**: `credential` must reference a credential linked to the workflow (per-workflow enforcement). A `totp` credential can be the same record (with both password and TOTP fields) or referenced via `totp_identifier`.
- **Reuse with profiles**: when the run is seeded from a `browser-profiles` profile that already holds a valid session, the `login` node SHALL short-circuit ("already authenticated") instead of re-logging-in.
- **Events**: emits `login_started`, the underlying `vision_step`s, and `login_completed` / `login_failed` with the outcome (never the secret).
- **UI**: NodeInspector renders a credential picker (linked credentials only), an optional URL, success criteria, and an optional TOTP identifier. RunLog shows a padlock icon and the login outcome.

## Capabilities

### New Capabilities

- `login-node`: the `login` node type, the scoped vision login sub-flow, credential + TOTP integration, profile short-circuit, the login events, and the NodeInspector form.

### Modified Capabilities

- `workflow-schema` (from `auto-agent-mvp`): `NodeType` gains `login`; a `LoginParams` model is added.
- `hybrid-executor` (from `auto-agent-mvp`): dispatch routes `login` to the scoped login sub-flow.
- `nl-workflow-planner` / `chat-authoring`: prompts document the `login` node and prefer it over hand-rolled `fill`/`click` login sequences.

## Impact

- **Backend**: a `login` handler that composes the vision agent with a focused prompt + the credential/TOTP services (~120 LOC). New events in the literal. No new dependency.
- **Frontend**: NodeInspector login form + RunLog padlock row.
- **Runtime**: a login is a short bounded vision sub-flow (typically 3–6 steps); cost is bounded like any vision node.
- **Migration**: additive node type; no DB migration. Secrets never logged.
- **Out of scope**: SSO/OAuth redirect dances beyond what the vision agent can click through; CAPTCHA at login (→ `captcha-antibot-proxy`); non-TOTP 2FA; credential discovery (the credential must be chosen explicitly).
