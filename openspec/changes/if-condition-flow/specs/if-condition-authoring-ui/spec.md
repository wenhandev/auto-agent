## Description

Canvas and inspector UX for adding and configuring IF (`condition`) branching and improving `switch` discoverability. Internal node type remains `condition`; localized display name is **IF / 条件**.

## User stories

- **As a workflow author**, I want to add an IF node from the canvas without using chat or editing JSON.
- **As a workflow author**, I want true/false branches visually labelled when I connect edges from an IF node.
- **As a workflow author**, I want a simple form to compare a variable to a value (e.g. status >= 400) without writing expression syntax.
- **As a workflow author**, I want an advanced expression mode for complex conditions using `{{= ... }}` with preview.

## ADDED Requirements

### Requirement: IF Node Palette Entry

The workflow editor SHALL expose a palette or toolbar action **"IF / 条件"** that inserts a node with `type: "condition"` and a human-readable label (default `"IF"` or localized equivalent).

#### Scenario: Insert IF from palette

- **WHEN** the author clicks "IF / 条件" on the workflow canvas
- **THEN** the editor SHALL add a `condition` node to the workflow JSON AND select it for inspection.

### Requirement: Auto-Created True And False Edges

When an IF node is inserted via the palette, the editor SHALL create two outgoing edges from that node:

- one with `when: "true"` (labelled **True / 是** in UI)
- one with `when: "false"` (labelled **False / 否** in UI)

Targets MAY be unset initially; the editor MAY show a validation hint for dangling edges but SHALL NOT block workflow save.

#### Scenario: New IF has two branches

- **WHEN** an IF node is inserted from the palette
- **THEN** the workflow SHALL contain exactly two new outgoing edges from that node with `when="true"` and `when="false"` respectively.

### Requirement: Condition Inspector Simple Mode

The NodeInspector for `condition` nodes SHALL provide a **Simple** mode with:

- **Left** — token/text field supporting `{{nodes...}}` variable insertion
- **Operator** — dropdown: `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not_in`, `is_truthy`, `is_falsy`
- **Right** — token/text field (hidden or disabled for unary ops)

Saving Simple mode SHALL persist a `predicate` object on the node params and SHOULD clear conflicting legacy bare `expr` unless the author switches to Advanced mode.

#### Scenario: Build predicate in inspector

- **WHEN** the author sets left=`{{nodes.http.output.status}}`, op=`>=`, right=`400` in Simple mode and saves
- **THEN** the node params SHALL contain `predicate: {left, op, right}`.

### Requirement: Condition Inspector Advanced Mode

The NodeInspector SHALL provide an **Advanced** mode with a multiline `expr` field accepting whole-field `{{= ... }}` expressions, placeholder hint text, and optional integration with `POST /api/expressions/preview` for best-effort preview against last run data.

When Advanced mode is saved with a non-empty `expr`, the editor SHOULD clear `predicate` OR display a warning that predicate takes precedence if both exist.

#### Scenario: Advanced expression saved

- **WHEN** the author enters `{{= nodes.n1.output.ok }}` in Advanced mode
- **THEN** the node params SHALL store `expr` with that value.

### Requirement: Canvas Visual Distinction For IF

IF (`condition`) nodes on the canvas SHALL be visually distinct from action nodes (existing amber styling) and SHALL show a branch icon. Outgoing handles SHALL use localized true/false labels when multiple source ports exist (existing `canvasPorts` behaviour).

#### Scenario: IF shows branch ports

- **WHEN** an IF node has two outgoing edges with `when` set
- **THEN** the canvas SHALL render separate source handles labelled for true and false branches.

### Requirement: Switch Palette Entry Optional

The editor SHOULD expose a **Switch / 分支** palette entry for `type: "switch"` with inspector field for `expr` and per-edge `case` editing on outgoing edges. This is optional for v1 if switch remains chat-authored, but IF palette is mandatory.

#### Scenario: Switch insert optional

- **WHEN** switch palette is implemented and author clicks Switch
- **THEN** a `switch` node is inserted with at least one default `case=null` edge.

### Requirement: Internationalization

UI strings for IF branching SHALL be localized in `en`, `zh-CN`, and `zh-TW` at minimum:

- Palette: IF / 条件
- Edge labels: True/False or 是/否
- Inspector section titles: Simple / Advanced or 简单 / 高级

#### Scenario: Chinese locale labels

- **WHEN** UI language is `zh-CN` and an IF node is displayed
- **THEN** palette and edge labels SHALL use Chinese strings from i18n files.

### Requirement: Planner And Chat Documentation

The NL planner / chat authoring prompts SHALL document:

- Use **IF (`condition`)** for flow branching (two paths).
- Use **Switch** for three or more mutually exclusive paths.
- Use **Filter** for removing items from a list, not for skipping workflow steps.

#### Scenario: Planner emits condition for binary branch

- **WHEN** a user asks to "skip login if already logged in"
- **THEN** the planner SHOULD propose a `condition` node with appropriate predicate or expression, not a linear-only graph.

## Out of Scope

- Visual "else if" chain wizard (authors chain IF nodes).
- Runtime changes to scheduler or evaluation (owned by `condition-safe-evaluation`).
- Automatic connection of false branch to `end` node.
