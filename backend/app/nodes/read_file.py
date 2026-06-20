from __future__ import annotations

from typing import Any

from app.nodes.result import Item
from app.tools.sandbox import SandboxViolation, resolve_sandbox_path


async def run(
    params: dict[str, Any],
    *,
    input_items: list[Item],
    context: dict[str, Any],
    workflow_id: str | None = None,
) -> list[Item]:
    if workflow_id is None:
        raise SandboxViolation("file actions require a persisted workflow")

    rel_path = str(params["path"])
    encoding = str(params.get("encoding", "utf-8"))
    max_bytes = int(params.get("max_bytes", 1_048_576))

    resolved = resolve_sandbox_path(rel_path, workflow_id=workflow_id)
    if not resolved.is_file():
        raise FileNotFoundError(f"file not found: {rel_path}")

    size = resolved.stat().st_size
    if size > max_bytes:
        raise ValueError(
            f"file size {size} exceeds max_bytes {max_bytes} for {rel_path!r}"
        )

    contents = resolved.read_text(encoding=encoding)
    byte_count = len(contents.encode(encoding))
    return [Item(json={"contents": contents, "byte_count": byte_count, "path": rel_path})]
