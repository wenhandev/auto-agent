## Description

A Google Sheets app descriptor on the framework: a Google OAuth2 credential type and the operations `values.get`, `values.append`, `values.update`, `values.clear`, `spreadsheets.create`. Custom hooks build A1 ranges from friendly fields and can map rows↔objects using a header row.

## User stories

- **As a workflow author**, I want to append items as rows to a sheet.
- **As a workflow author**, I want to read a range and get one item per row (objects keyed by the header row).

## ADDED Requirements

### Requirement: Sheets OAuth2 Credential And Operations

The Sheets descriptor SHALL declare a Google OAuth2 credential (spreadsheets scope, bearer injection) and expose `values.get`, `values.append`, `values.update`, `values.clear`, `spreadsheets.create`. `values.append`/`values.update` SHALL emit the update summary (`root_path`).

#### Scenario: Append rows

- **WHEN** a `values.append` node runs with a `spreadsheet_id`, `range`, and items
- **THEN** it SHALL POST the values to the Sheets API AND emit one item with the update summary.

### Requirement: Rows To Objects Mapping

For `values.get`, a custom hook SHALL optionally map the `{values: [[...]]}` matrix into one item per data row, keyed by the header row when `as_objects` is enabled; otherwise it SHALL emit one item with the raw matrix.

#### Scenario: Read range as objects

- **WHEN** `values.get` returns `[["name","age"],["a","1"],["b","2"]]` with `as_objects: true`
- **THEN** the node SHALL emit two items: `{"name":"a","age":"1"}` and `{"name":"b","age":"2"}`.

## Out of Scope

- Sheets change triggers.
- Cell formatting / charts / pivot APIs.
