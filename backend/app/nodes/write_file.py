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
    contents = str(params.get("contents", ""))
    encoding = str(params.get("encoding", "utf-8"))

    resolved = resolve_sandbox_path(rel_path, workflow_id=workflow_id)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(contents, encoding=encoding)
    byte_count = len(contents.encode(encoding))
    return [Item(json={"path": rel_path, "byte_count": byte_count})]
