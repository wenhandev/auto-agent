from __future__ import annotations

from typing import Any, Awaitable, Callable

from app.nodes.result import Item
from app.services import sub_runs


async def run(
    params: dict[str, Any],
    *,
    input_items: list[Item],
    context: dict[str, Any],
    node_id: str,
    emit: Callable[..., Awaitable[None]] | None = None,
    abort_event: Any = None,
    session: Any = None,
    workflow_id: str | None = None,
    run_id: str | None = None,
) -> list[Item]:
    if run_id is None:
        raise ValueError("subworkflow requires a persisted run (run_id)")

    target_wf_id = str(params["workflow_id"])
    version_id = params.get("version_id")
    input_data = params.get("input") or {}
    if not isinstance(input_data, dict):
        raise ValueError("subworkflow input must be a dict")

    child_version_id = str(version_id) if version_id else None

    if emit is not None:
        await emit(
            "subworkflow_started",
            node_id=node_id,
            child_workflow_id=target_wf_id,
            child_version_id=child_version_id or "",
        )

    result = await sub_runs.run_subworkflow(
        parent_run_id=run_id,
        workflow_id=target_wf_id,
        version_id=child_version_id,
        input_data=input_data,
        session=session,
        emit=emit,
        abort_event=abort_event,
    )

    from app.services import cost_tracking as cost_svc

    cost_svc.rollup_child_to_parent(
        parent_run_id=run_id,
        child_run_id=result.child_run_id,
        parent_node_id=node_id,
        session=session,
    )

    output = {
        "child_run_id": result.child_run_id,
        "status": result.status,
        "final_output": result.final_output,
    }

    if emit is not None:
        await emit(
            "subworkflow_completed",
            node_id=node_id,
            child_run_id=result.child_run_id,
            status=result.status,
            final_output=result.final_output,
        )

    return [Item(json=output)]
