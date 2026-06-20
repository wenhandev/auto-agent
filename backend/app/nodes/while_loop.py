from __future__ import annotations

from typing import Any, Awaitable, Callable

from app.nodes._helpers import build_namespace, eval_value
from app.nodes.result import Item, NodeResult
from app.schemas import Workflow
from app.services.predicate import PredicateError, evaluate_predicate

_HARD_CEILING = 1000


async def _predicate_holds(
    predicate: dict[str, Any],
    *,
    input_items: list[Item],
    context: dict[str, NodeResult],
    iteration: int,
) -> bool:
    ns = build_namespace(
        input_items[0] if input_items else Item(json={}),
        input_items,
        context,
    )
    ns["iteration"] = iteration
    left = eval_value(predicate.get("left"), ns)
    op = str(predicate.get("op", "=="))
    right = (
        eval_value(predicate.get("right"), ns)
        if "right" in predicate
        else predicate.get("right")
    )
    try:
        return evaluate_predicate(left, op, right)
    except PredicateError as exc:
        raise ValueError(str(exc)) from exc


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
    predicate = params.get("predicate")
    if not isinstance(predicate, dict):
        raise ValueError("while_loop requires predicate object")

    max_iterations = min(int(params.get("max_iterations", 100)), _HARD_CEILING)
    if max_iterations < 1:
        raise ValueError("while_loop max_iterations must be >= 1")

    body_raw = params.get("body_workflow")
    if not isinstance(body_raw, dict):
        raise ValueError("while_loop requires body_workflow as a Workflow dict")
    body = Workflow.model_validate(body_raw)

    for node in body.nodes:
        if node.type in ("foreach", "while_loop"):
            raise ValueError(
                f"nested {node.type} inside body_workflow is not allowed (node {node.id})"
            )

    if run_node is None:
        raise RuntimeError("while_loop requires run_node callback")

    from app.exec.scheduler import execute_dag

    results: list[Any] = []
    succeeded = 0
    failed = 0
    iteration = 0
    max_reached = False

    while iteration < max_iterations:
        if abort_event is not None and abort_event.is_set():
            raise RuntimeError("run aborted during while_loop")

        if not await _predicate_holds(
            predicate,
            input_items=input_items,
            context=context,
            iteration=iteration,
        ):
            break

        if emit is not None:
            await emit(
                "while_iteration_started",
                node_id=node_id,
                index=iteration,
            )

        iter_context: dict[str, NodeResult] = dict(context)
        iter_context[node_id] = NodeResult.single(
            {"iteration": iteration, "is_last": False}
        )

        last_completed: Any = None
        body_ok = False

        async def tracking_emit(payload: dict) -> None:
            nonlocal last_completed, body_ok
            ev = payload.get("event")
            if ev == "node_completed":
                last_completed = payload.get("output")
            elif ev in ("run_completed", "run_completed_with_errors"):
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
                raise RuntimeError("while_loop body workflow did not complete successfully")
            succeeded += 1
            iteration_ok = True
        except Exception:
            failed += 1
            iteration_ok = False
            if emit is not None:
                await emit(
                    "while_iteration_completed",
                    node_id=node_id,
                    index=iteration,
                    output=None,
                    succeeded=False,
                )
            raise

        results.append(last_completed)
        iteration += 1
        if emit is not None:
            await emit(
                "while_iteration_completed",
                node_id=node_id,
                index=iteration - 1,
                output=last_completed,
                succeeded=iteration_ok,
            )

        if iteration >= max_iterations and await _predicate_holds(
            predicate,
            input_items=input_items,
            context=context,
            iteration=iteration,
        ):
            max_reached = True
            break

    output: dict[str, Any] = {
        "iterations": iteration,
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }
    if max_reached:
        output["max_iterations_reached"] = True
        output["reason"] = "max_iterations_reached"
    return [Item(json=output)]
