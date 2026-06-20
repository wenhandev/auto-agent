## Context

`node-context-variables` established the `{{...}}` chained resolver and a per-run context. Triggers already attach a `run.context_json`. What's missing is a *declared, typed, validated* input surface so a workflow is a true reusable template. Skyvern's `WorkflowParameter` (and `RESERVED_PARAMETER_KEYS`) is the reference shape; `REFERENCES.md` already flags aligning reserved names across changes.

## Goals / Non-Goals

**Goals:**
- Declared, typed inputs validated *before* a run starts.
- One canonical `{{params.<name>}}` token.
- Typed Run-Now form + API/trigger value passing.

**Non-Goals:**
- Computed/dependent parameters.
- File-upload parameters (→ `vision-and-utility-blocks`).
- An expression language (resolver stays dot/index only, per `node-context-variables`).

## Decisions

### Decision 1: Parameters live in `workflow_json`, validated pre-run
Declarations are part of the versioned workflow; supplied values are validated in `services.runs` before enqueue.
- **Why**: a missing required param should fail fast with a clear message, not mid-run as a `node_failed`. Versioned declarations keep runs reproducible.

### Decision 2: `{{params.<name>}}` in the chain, ordered params→nodes→cred
The resolver adds the params family first.
- **Why**: distinct prefix avoids collisions; documenting order keeps behaviour deterministic. Aligns reserved names (`params`/`nodes`/`cred`/`run`/`trigger`) across changes per `REFERENCES.md`.

### Decision 3: `secret`-typed params are masked and may reference a credential
A `secret` param value is masked in `Run.parameters_json`, run events, and traces; it can hold a literal secret or a `{{cred...}}` reference resolved at use.
- **Why**: parameterised secrets (e.g. a per-run token) without leaking into history.

### Decision 4: Type set kept small and JSON-native
`string|number|boolean|secret|json`. `json` covers arrays/objects for advanced use.
- **Why**: matches the JSON transport; avoids a sprawling type system.

### Decision 5: Trigger body → params mapping, passthrough to context
Webhook triggers map named body fields onto declared params; unmapped fields remain in `run.context_json` (backward compatible with `triggers-and-scheduling`).
- **Why**: declared params get validation; arbitrary extras still available, no breakage.

## Risks / Trade-offs

- [Validation gaps for `json` type] → validate it parses as JSON of the declared shape if a sub-schema is later added; v1 accepts any JSON.
- [Secret in `parameters_json`] → mandatory masking; same masker as credentials.
- [Reserved-name collision] → `params` reserved; the editor prompt forbids declaring a param literally named to shadow `nodes`/`cred`.
- [Old workflows] → no declared params ⇒ unchanged behaviour.

## Migration Plan

- Additive `Workflow.parameters` in `workflow_json`; `Run.parameters_json` column (default `{}`).
- Resolver gains the `{{params...}}` family.
- Run-Now dialog renders the typed form when parameters are declared.

## Open Questions

- Per-parameter validation rules (regex/min/max/enum)? (Lean: add an optional `constraints` object later; v1 is type-only.)
- Should a declared `secret` param auto-create a credential, or only reference one? (Lean: reference-or-literal; no auto-create.)
