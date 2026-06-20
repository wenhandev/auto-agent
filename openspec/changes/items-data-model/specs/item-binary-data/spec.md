## Description

Items carry binary payloads (downloaded files, PDFs, screenshots) under named keys via `BinaryRef`. Small payloads are stored inline as base64; larger payloads reference the artifact store (or a sandboxed temp file when the artifact store is absent). Binary is passed through the graph with items and is never interpolated into string params.

## User stories

- **As a workflow author**, I want a `file_download` node to attach the downloaded bytes to its item so a later `send_email` or `write_file` node can consume them.
- **As an operator**, I do not want multi-megabyte file bytes serialised into the run-event stream or the SQLite DB.
- **As a developer of a downstream node**, I want one typed way to read a predecessor's binary regardless of whether it was stored inline or as an artifact.

## ADDED Requirements

### Requirement: BinaryRef Model And Storage Tiering

A binary payload SHALL be represented by `BinaryRef { kind: "inline" | "artifact", mime: str, size: int, filename: str | null, data_b64?: str, artifact_id?: str }`. When `size <= INLINE_BINARY_MAX` (default 256 KB), `kind` SHALL be `"inline"` and the bytes SHALL be base64 in `data_b64`. When larger, `kind` SHALL be `"artifact"`: bytes SHALL be stored in the artifact store (when `run-artifacts-observability` is active) and referenced by `artifact_id`, otherwise written to a sandboxed temp file under `backend/data/workflow_files/_binary/` and referenced by a file-path id.

#### Scenario: Small payload stored inline

- **WHEN** a node attaches a 12 KB PNG with the default 256 KB threshold
- **THEN** the `BinaryRef` SHALL have `kind == "inline"`, `mime == "image/png"`, `size == 12288`, and a non-null `data_b64`.

#### Scenario: Large payload referenced, not inlined

- **WHEN** a node attaches a 5 MB PDF and the artifact store is absent
- **THEN** the `BinaryRef` SHALL have `kind == "artifact"`, a null `data_b64`, and an `artifact_id` pointing at a sandboxed temp file under `backend/data/workflow_files/_binary/`.

### Requirement: Binary Passthrough Between Nodes

When the executor threads `input_items` from a predecessor to a node, the items' `binary` maps SHALL be carried through unchanged. A node that does not modify binary SHALL forward it; a node that adds binary SHALL merge under a new key.

#### Scenario: Binary survives a passthrough node

- **WHEN** node `download` emits an item with `binary={"data": <ref>}` and the next node is a deterministic node that does not touch binary
- **THEN** that node's emitted item SHALL still contain `binary["data"]` equal to the same `BinaryRef`.

### Requirement: Binary Is Never String-Interpolated

A `{{nodes.<id>.item.binary.<name>}}` (or any token resolving to a `BinaryRef`) SHALL raise `VariableResolutionError` with a message instructing the author to consume binary via a file node, NOT silently stringify the bytes.

#### Scenario: Binary token rejected

- **WHEN** a param value is `"{{nodes.download.item.binary.data}}"`
- **THEN** resolution SHALL raise `VariableResolutionError` whose message contains `"binary values cannot be interpolated into text"`.

### Requirement: Binary Summary In Events And `items` Tokens

Wherever items are summarised (the `node_completed.items_preview`, and a `{{nodes.<id>.items}}` whole-token resolution), binary SHALL appear only as a summary `{name: {mime, size, filename}}` and SHALL NOT include `data_b64` or raw bytes.

#### Scenario: Event preview summarises binary

- **WHEN** an item has `binary={"data": BinaryRef(kind="inline", mime="application/pdf", size=4096, filename="r.pdf", data_b64="...")}`
- **THEN** the event's `items_preview.binary` SHALL be `{"data": {"mime": "application/pdf", "size": 4096, "filename": "r.pdf"}}` with no `data_b64`.

## Out of Scope

- Object-storage backends (S3 / GCS) for binary — local disk / artifact store only, consistent with `run-artifacts-observability`.
- Binary transformation nodes (image resize, PDF merge) — future change.
- Deduplication of identical binaries across items — not in v1.
