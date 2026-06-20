from __future__ import annotations

from typing import Any, Awaitable, Callable

from app.nodes.result import Item, NodeResult
from app.schemas import Workflow


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
    run_node: Any = None,
) -> list[Item]:
    """Iterate items and run an inline body workflow per item (sequential v1)."""
    items = params.get("items")
    if not isinstance(items, list):
        raise ValueError(f"foreach items must be a list, got {type(items).__name__}")

    max_iterations = int(params.get("max_iterations", 1000))
    if params.get("parallel") is True:
        raise ValueError("foreach parallel=True is not supported in v1")

    if len(items) > max_iterations:
        raise ValueError(
            f"foreach exceeds max_iterations: {len(items)} > {max_iterations}"
        )

    body_raw = params.get("body_workflow")
    if not isinstance(body_raw, dict):
        raise ValueError("foreach requires body_workflow as a Workflow dict")
    body = Workflow.model_validate(body_raw)

    for node in body.nodes:
        if node.type == "foreach":
            raise ValueError(
                f"nested foreach inside body_workflow is not allowed (node {node.id})"
            )

    if run_node is None:
        raise RuntimeError("foreach requires run_node callback")

    from app.exec.scheduler import execute_dag

    results: list[Any] = []
    succeeded = 0
    failed = 0

    for index, item in enumerate(items):
        if abort_event is not None and abort_event.is_set():
            raise RuntimeError("run aborted during foreach")

        if emit is not None:
            await emit(
                "foreach_iteration_started",
                node_id=node_id,
                index=index,
                item=item,
            )

        iter_context: dict[str, NodeResult] = dict(context)
        iter_context[node_id] = NodeResult.single(
            {"item": item, "index": index, "is_last": index == len(items) - 1}
        )

        last_completed: Any = None
        body_ok = False

        async def tracking_emit(payload: dict) -> None:
            nonlocal last_completed, body_ok
            ev = payload.get("event")
            if ev == "node_completed":
                last_completed = payload.get("output")
            elif ev == "run_completed":
                body_ok = True
            elif ev in ("run_completed_with_errors",):
                body_ok = True
            elif ev in ("run_failed", "run_aborted"):
                body_ok = False

        async def inner_run_node(
            node,
            emit_fn,
            *,
            input_items: list[Item],
            context: dict[str, NodeResult],
            session=None,
            workflow_id=None,
            abort_event=None,
        ):
            return await run_node(
                node,
                emit_fn,
                input_items=input_items,
                context=context,
                session=session,
                workflow_id=workflow_id,
                abort_event=abort_event,
            )

        try:
            await execute_dag(
                body,
                tracking_emit,
                run_node=inner_run_node,
                abort_event=abort_event,
                session=session,
                workflow_id=workflow_id,
                initial_context=iter_context,
            )
            if not body_ok:
                raise RuntimeError("foreach body workflow did not complete successfully")
            succeeded += 1
            iteration_ok = True
        except Exception:
            failed += 1
            iteration_ok = False
            if emit is not None:
                await emit(
                    "foreach_iteration_completed",
                    node_id=node_id,
                    index=index,
                    output=None,
                    succeeded=False,
                )
            raise

        results.append(last_completed)
        if emit is not None:
            await emit(
                "foreach_iteration_completed",
                node_id=node_id,
                index=index,
                output=last_completed,
                succeeded=iteration_ok,
            )

    output = {
        "item_count": len(items),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }
    return [Item(json=output)]
