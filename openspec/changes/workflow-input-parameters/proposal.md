## depends_on

- `auto-agent-platform` — `Workflow` / `WorkflowVersion` persistence, `Run` table, `POST /api/runs`, chat editor.
- `node-context-variables` — the `{{...}}` interpolation pass this change extends with a `{{params.<name>}}` family and the per-run context.
- `triggers-and-scheduling` (soft) — triggers can supply parameter values; the webhook body maps onto declared params.

Consumed by `vision-and-utility-blocks`, `public-api-and-auth` (`run-task`/workflow run pass parameters), and `expanded-node-library` (`foreach`/`subworkflow` pass values).

## Why

Skyvern workflows are **reusable templates** you "run repeatedly with different parameters". `auto-agent` workflows are static: to change the search term or the target account you edit the node params and save a new version. There is no declared, typed **input surface**. Triggers can attach a `run.context_json`, but there is no schema, no UI form, no validation, and no canonical token to read a value.

This change adds declared, typed **workflow input parameters**: a workflow defines its inputs once; every run (manual/API/trigger) supplies values; nodes read them via `{{params.<name>}}`.

## What Changes

- **Schema**: `Workflow` (in `workflow_json`) gains a `parameters: list[WorkflowParameter]` where `WorkflowParameter = {name, type ∈ {string,number,boolean,secret,json}, label?, required?, default?, description?}`. `secret`-typed params are masked in run history and traces and may reference a credential. Additive; no DB migration (lives in `workflow_json`).
- **Token family**: `{{params.<name>}}` resolves from the run's supplied parameter values, in the same chained interpolation pass as `{{nodes...}}` / `{{cred...}}`. Missing required param without a default → the run is rejected before it starts (not a mid-run `node_failed`).
- **Run inputs**: `POST /api/runs` (and `/api/v1/.../run`, trigger enqueues) accept `parameters: dict[str, Any]`. Values are validated against the declared types; defaults fill omitted optionals; the resolved set is persisted on the `Run` (`Run.parameters_json`, secrets masked).
- **Trigger mapping**: a webhook trigger maps its incoming body onto declared params (by name, with a documented passthrough for unmapped fields into `run.context_json`); a cron trigger carries a fixed parameter set.
- **UI**: a "参数" tab on the workflow detail page to declare parameters; the Run-Now dialog renders a typed form from the declared parameters (with defaults pre-filled and required validation); run detail shows the parameter values used (secrets masked). The NodeInspector "可用变量" tab (from `node-context-variables`) lists `{{params.<name>}}` alongside node outputs.

## Capabilities

### New Capabilities

- `workflow-parameters`: the `WorkflowParameter` schema, the `{{params.<name>}}` token family, pre-run validation, the run-inputs API, `Run.parameters_json` persistence (masked secrets), the declare-params UI, and the Run-Now typed form.

### Modified Capabilities

- `workflow-schema` (from `auto-agent-mvp`): `Workflow` gains `parameters`.
- `node-output-interpolation` (from `node-context-variables`): the chained resolver adds the `{{params...}}` family; chain order documented (params, nodes, then credentials).
- `run-history` (from `auto-agent-platform`): `Run` persists `parameters_json` (masked); run detail shows inputs.
- `workflow-triggers` (from `triggers-and-scheduling`): triggers can supply/map parameter values.
- `chat-authoring` (from `auto-agent-platform`): editor prompt documents declaring + referencing parameters.

## Impact

- **Backend**: schema additions, resolver extension, pre-run validation in `services.runs`, `Run.parameters_json` column (additive). Tests: type validation, required/default handling, secret masking, token resolution, trigger mapping.
- **Frontend**: "参数" declare tab, Run-Now typed form, run-detail inputs row, variable-picker entries.
- **Runtime**: validation is one pass before enqueue; resolution is part of the existing per-node interpolation walk.
- **Migration**: `Run.parameters_json` added (default `{}`); existing workflows have no declared params and behave unchanged.
- **Out of scope**: parameter dependencies / computed defaults; file-typed parameters (upload) — defer to `vision-and-utility-blocks`' `file_upload`; cross-workflow parameter inheritance beyond `subworkflow` input passing (that's `expanded-node-library`).
