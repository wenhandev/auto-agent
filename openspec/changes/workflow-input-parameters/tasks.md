## 1. Schema

- [x] 1.1 Add `WorkflowParameter` model and `Workflow.parameters: list[WorkflowParameter]`
- [x] 1.2 Add `Run.parameters_json` column (additive, default `{}`)

## 2. Validation & resolution

- [x] 2.1 Pre-run validation in `services.runs` (types, required, defaults) — reject before enqueue
- [x] 2.2 Add `{{params.<name>}}` to the chained resolver (order: params, nodes, cred)
- [x] 2.3 Persist resolved parameters on the run with secret masking
- [x] 2.4 Tests: type validation, required/default, masking, token resolution

## 3. Entry points

- [x] 3.1 `POST /api/runs` + `/api/v1/.../run` accept `parameters`
- [x] 3.2 Webhook trigger maps body → declared params; passthrough to `context_json`
- [x] 3.3 Cron trigger carries a fixed parameter set

## 4. Frontend

- [ ] 4.1 "参数" declare tab on the workflow detail page
- [x] 4.2 Run-Now typed form generated from declared parameters (defaults + required validation)
- [ ] 4.3 Run detail shows parameter values used (secrets masked)
- [ ] 4.4 NodeInspector "可用变量" lists `{{params.<name>}}`

## 5. Prompts

- [ ] 5.1 Editor prompt documents declaring + referencing parameters; forbids shadowing reserved names
