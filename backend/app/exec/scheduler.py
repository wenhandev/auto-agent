"""Indegree ready-queue scheduler for DAG workflow execution.

This module owns *traversal*: it tracks which incoming edges to each node are
resolved (selected or pruned), runs a node when all its incoming edges are
resolved and at least one was selected, and skips a node (propagating the skip
to its outgoing edges) when every incoming edge was pruned. It also performs
edge selection for ``condition``/``switch`` nodes and waits for the required
parents of a ``merge`` node.

Per-node behaviour (param interpolation, the ``_run_node`` dispatch,
self-heal, retry/on-error, the items envelope, and the ``node_completed``
payload shape) stays in :mod:`app.executor`; the scheduler invokes the
``run_node`` callback for those so that linear and ``condition``-only
workflows execute identically to before.
"""
from __future__ import annotations

import asyncio
import heapq
from typing import Any, Awaitable, Callable, Optional

from sqlmodel import Session

from app.nodes.result import Item, NodeResult
from app.schemas import Edge, Node, Workflow
from app.services.credential_interpolation import CredentialResolutionError
from app.services.variable_interpolation import VariableResolutionError
from app.settings import settings

Emit = Callable[..., Awaitable[None]]

# run_node(...) -> NodeOutcome
RunNode = Callable[..., Awaitable[Any]]

_BROWSER_NODE_TYPES = frozenset({
    "navigate",
    "click",
    "fill",
    "wait",
    "extract",
    "vision_navigate",
    "vision_act",
    "vision_extract",
    "fuzzy_action",
    "goto_url",
    "print_page",
    "file_upload",
    "file_download",
    "login",
})


async def _browser_screenshot_extra(node_id: str, phase: str) -> dict[str, Any]:
    from app.services.browser_visual import skip_optional_page_screenshots

    if skip_optional_page_screenshots():
        return {}
    from app.services import artifact_context
    from app.services import artifacts as artifact_svc

    if artifact_context.get_run_id() is None:
        return {}
    artifact_id = await artifact_svc.capture_page_screenshot(
        artifact_context.get_run_id() or "",
        node_id=node_id,
        phase=phase,
    )
    return {"artifact_id": artifact_id} if artifact_id else {}


class SwitchNoMatch(Exception):
    """Raised when a ``switch`` evaluates to a key with no matching/default edge."""


class _RunFailed(Exception):
    """Internal signal that a node failed; carries the ``run_failed`` message."""


def _topo_ranks(
    node_ids: list[str],
    incoming: dict[str, list[Edge]],
    outgoing: dict[str, list[Edge]],
) -> Optional[dict[str, int]]:
    """Kahn's algorithm. Returns deterministic ranks, or ``None`` on a cycle.

    A node's rank is strictly greater than every parent's rank, so ordering the
    ready set by ``(rank, node_id)`` is a valid, reproducible topological order.
    """
    present = set(node_ids)
    indeg: dict[str, int] = {
        nid: sum(1 for e in incoming.get(nid, []) if e.source in present)
        for nid in node_ids
    }
    heap = [nid for nid in node_ids if indeg[nid] == 0]
    heapq.heapify(heap)
    ranks: dict[str, int] = {}
    counter = 0
    while heap:
        nid = heapq.heappop(heap)
        ranks[nid] = counter
        counter += 1
        for e in outgoing.get(nid, []):
            tgt = e.target
            if tgt in indeg:
                indeg[tgt] -= 1
                if indeg[tgt] == 0:
                    heapq.heappush(heap, tgt)
    if len(ranks) < len(node_ids):
        return None
    return ranks


def _select_outgoing(
    node: Node, outgoing: list[Edge], result: NodeResult
) -> tuple[list[Edge], list[Edge]]:
    """Decide which outgoing edges are selected vs pruned for a completed node."""
    if not outgoing:
        return [], []
    if node.type == "end":
        # Reaching an end terminates this path; never traverse past it.
        return [], list(outgoing)
    out = result.output if isinstance(result.output, dict) else {}
    if node.type == "condition":
        branch = "true" if bool(out.get("condition")) else "false"
        pick = next((e for e in outgoing if e.when == branch), None)
        if pick is None:
            pick = next((e for e in outgoing if e.when is None), None)
        if pick is None:
            pick = outgoing[0]
        pruned = [e for e in outgoing if e is not pick]
        return [pick], pruned
    if node.type == "switch":
        key = str(out.get("switch_case"))
        pick = next((e for e in outgoing if e.case == key), None)
        if pick is None:
            pick = next((e for e in outgoing if e.case is None), None)
        if pick is None:
            raise SwitchNoMatch(
                f"switch: no case matched {key!r} and no default edge"
            )
        pruned = [e for e in outgoing if e is not pick]
        return [pick], pruned
    # Plain node: follow only kind="next" edges; prune on_error edges.
    next_edges = [e for e in outgoing if e.kind == "next"]
    on_error_edges = [e for e in outgoing if e.kind == "on_error"]
    return list(next_edges), list(on_error_edges)


def _select_on_error_edges(
    node: Node, outgoing: list[Edge], policy: str
) -> tuple[Optional[list[Edge]], Optional[list[Edge]], Optional[str]]:
    """Pick edges after a tolerated failure. Returns (selected, pruned, degrade_note)."""
    if policy == "continue":
        next_edges = [e for e in outgoing if e.kind == "next"]
        if not next_edges:
            return None, None, f"on_error=continue but no next edge from node {node.id}"
        pick = next_edges[0]
        pruned = [e for e in outgoing if e is not pick]
        return [pick], pruned, None
    if policy == "branch":
        on_error_edges = [e for e in outgoing if e.kind == "on_error"]
        if not on_error_edges:
            return None, None, (
                f"on_error=branch but no on_error edge from node {node.id}; "
                "falling back to fail_run"
            )
        pick = on_error_edges[0]
        pruned = [e for e in outgoing if e is not pick]
        return [pick], pruned, None
    return None, None, None


async def execute_dag(
    workflow: Workflow,
    emit: Emit,
    *,
    run_node: RunNode,
    abort_event: Optional[asyncio.Event] = None,
    session: Optional[Session] = None,
    workflow_id: Optional[str] = None,
    run_id: Optional[str] = None,
    initial_context: Optional[dict[str, NodeResult]] = None,
) -> None:
    """Drive the workflow to completion, emitting events via ``emit``.

    Assumes the caller already emitted ``run_started``. Emits ``run_completed``
    on success, ``run_failed`` on node/cycle failure, and ``run_aborted`` when
    the abort event is set. ``run_node`` performs per-node interpolation and
    dispatch (returning a :class:`NodeResult`); ``merge`` nodes are combined
    in-scheduler from their arrived parents.
    """
    from app import executor  # lazy import to avoid an import cycle

    max_items = settings.max_items_per_node

    nodes_by_id: dict[str, Node] = {n.id: n for n in workflow.nodes}
    outgoing: dict[str, list[Edge]] = {}
    incoming: dict[str, list[Edge]] = {}
    for e in workflow.edges:
        outgoing.setdefault(e.source, []).append(e)
        incoming.setdefault(e.target, []).append(e)

    ranks = _topo_ranks(list(nodes_by_id.keys()), incoming, outgoing)
    if ranks is None:
        await emit("run_failed", error="cycle detected in workflow graph")
        return

    context: dict[str, NodeResult] = dict(initial_context or {})
    edge_state: dict[str, str] = {e.id: "pending" for e in workflow.edges}
    pending_in: dict[str, int] = {
        nid: len(incoming.get(nid, [])) for nid in nodes_by_id
    }
    done: set[str] = set()
    ready: set[str] = set()
    had_tolerated_failure = False
    failed_node_ids: list[str] = []

    if workflow.start_id not in nodes_by_id:
        await emit(
            "run_failed", error=f"node {workflow.start_id!r} not found in workflow"
        )
        return
    ready.add(workflow.start_id)

    async def _resolve_edge(edge: Edge) -> None:
        tgt = edge.target
        if tgt not in pending_in:
            return
        pending_in[tgt] -= 1
        tnode = nodes_by_id.get(tgt)
        if pending_in[tgt] > 0:
            if tnode is not None and tnode.type == "merge":
                arrived = sum(
                    1
                    for ie in incoming.get(tgt, [])
                    if edge_state.get(ie.id) == "selected"
                )
                await emit(
                    "merge_waiting",
                    node_id=tgt,
                    arrived=arrived,
                    expected=len(incoming.get(tgt, [])),
                )
            return
        await _on_resolved(tgt)

    async def _on_resolved(tgt: str) -> None:
        if tgt in done or tgt in ready:
            return
        any_selected = any(
            edge_state.get(ie.id) == "selected" for ie in incoming.get(tgt, [])
        )
        if any_selected:
            ready.add(tgt)
            return
        # Every incoming edge pruned -> skip this node and propagate the skip.
        done.add(tgt)
        await emit("node_skipped", node_id=tgt)
        for oe in outgoing.get(tgt, []):
            edge_state[oe.id] = "pruned"
            await emit("branch_pruned", node_id=tgt, edge_id=oe.id)
            await _resolve_edge(oe)

    async def _execute(node: Node) -> tuple[Optional[NodeResult], list[Edge], list[Edge]]:
        nonlocal had_tolerated_failure, failed_node_ids

        started_extra: dict[str, Any] = {}
        if node.type in _BROWSER_NODE_TYPES:
            started_extra = await _browser_screenshot_extra(node.id, "start")
        await emit("node_started", node_id=node.id, **started_extra)

        selected_parents: list[tuple[Edge, NodeResult]] = [
            (e, context[e.source])
            for e in incoming.get(node.id, [])
            if edge_state.get(e.id) == "selected" and e.source in context
        ]

        if node.type == "merge":
            combined: list[Item] = []
            for _, res in selected_parents:
                combined.extend(res.items)
            input_items = combined or [Item(json={})]
        elif selected_parents:
            input_items = selected_parents[0][1].items or [Item(json={})]
        else:
            input_items = [Item(json={})]

        if node.type == "merge":
            try:
                result = executor._merge_result(node, selected_parents)
            except Exception as exc:
                await emit("node_failed", node_id=node.id, error=str(exc))
                raise _RunFailed(f"node {node.id} failed: {exc}")
            attempts = 1
        elif node.type == "approval":
            if run_id is None:
                await emit(
                    "node_failed",
                    node_id=node.id,
                    error="approval node requires a persisted run_id",
                )
                raise _RunFailed(f"node {node.id} failed: approval requires run_id")
            try:
                result = await executor._handle_approval_node(
                    node,
                    emit,
                    run_id=run_id,
                    workflow_id=workflow_id,
                    abort_event=abort_event,
                    session=session,
                )
            except executor._RunRejected:
                await emit("run_rejected")
                raise executor._RunRejected()
            except executor._RunAborted:
                raise
            except Exception as exc:
                await emit("node_failed", node_id=node.id, error=str(exc))
                raise _RunFailed(f"node {node.id} failed: {exc}")
            attempts = 1
        else:
            try:
                outcome = await run_node(
                    node,
                    emit,
                    input_items=input_items,
                    context=context,
                    session=session,
                    workflow_id=workflow_id,
                    abort_event=abort_event,
                )
            except executor._RunAborted:
                raise
            except Exception as exc:
                await emit("node_failed", node_id=node.id, error=str(exc))
                raise _RunFailed(f"node {node.id} failed: {exc}")

            if outcome.kind == "completed":
                result = outcome.result
                assert result is not None
                attempts = outcome.attempts
            else:
                exc = outcome.error
                assert exc is not None
                error_str = str(exc)
                on_error = node.on_error
                selected_err: list[Edge] = []
                pruned_err: list[Edge] = []

                if on_error in ("continue", "branch"):
                    sel, pru, degrade_note = _select_on_error_edges(
                        node, outgoing.get(node.id, []), on_error
                    )
                    if degrade_note is not None:
                        error_str = f"{error_str}; {degrade_note}"
                        on_error = "fail_run"
                    else:
                        selected_err = sel or []
                        pruned_err = pru or []

                failed_kwargs: dict[str, Any] = {
                    "node_id": node.id,
                    "error": error_str,
                    "error_kind": type(exc).__name__,
                }
                if node.retry is not None:
                    failed_kwargs["attempt"] = outcome.attempts
                await emit("node_failed", **failed_kwargs)

                if on_error == "fail_run":
                    raise _RunFailed(f"node {node.id} failed: {error_str}")

                context[node.id] = executor._error_context_entry(
                    exc, outcome.attempts
                )
                had_tolerated_failure = True
                failed_node_ids.append(node.id)
                return None, selected_err, pruned_err

        if len(result.items) > max_items:
            msg = f"item cap {max_items} exceeded by node {node.id}"
            await emit("node_failed", node_id=node.id, error=msg)
            raise _RunFailed(f"node {node.id} failed: {msg}")

        validation_branch: tuple[list[Edge], list[Edge]] | None = None
        if node.type == "validation":
            out = result.output if isinstance(result.output, dict) else {}
            if not out.get("passed"):
                await emit(
                    "validation_failed",
                    node_id=node.id,
                    reason=out.get("reason"),
                    checked=out.get("checked"),
                )
                on_error = node.on_error
                if on_error == "fail_run":
                    await emit(
                        "node_failed",
                        node_id=node.id,
                        error=out.get("reason") or "validation failed",
                        error_kind="ValidationFailed",
                    )
                    raise _RunFailed(
                        f"node {node.id} failed: {out.get('reason') or 'validation failed'}"
                    )
                if on_error == "branch":
                    sel, pru, degrade_note = _select_on_error_edges(
                        node, outgoing.get(node.id, []), "branch"
                    )
                    if degrade_note is not None:
                        await emit(
                            "node_failed",
                            node_id=node.id,
                            error=f"{out.get('reason')}; {degrade_note}",
                            error_kind="ValidationFailed",
                        )
                        raise _RunFailed(
                            f"node {node.id} failed: {out.get('reason')}; {degrade_note}"
                        )
                    validation_branch = (sel or [], pru or [])

        # Compute edge selection BEFORE node_completed so a non-matching switch
        # surfaces as a node failure rather than a (misleading) completion.
        try:
            if validation_branch is not None:
                selected, pruned = validation_branch
            else:
                selected, pruned = _select_outgoing(
                    node, outgoing.get(node.id, []), result
                )
        except SwitchNoMatch as exc:
            await emit("node_failed", node_id=node.id, error=str(exc))
            raise _RunFailed(f"node {node.id} failed: {exc}")

        context[node.id] = result
        completed_kwargs: dict[str, Any] = {
            "node_id": node.id,
            "output": result.output,
            "items_count": len(result.items),
            "items_preview": result.items[0].to_summary() if result.items else {"json": {}},
        }
        if node.retry is not None:
            completed_kwargs["attempt"] = attempts
        if node.type in _BROWSER_NODE_TYPES:
            completed_extra = await _browser_screenshot_extra(node.id, "end")
            completed_kwargs.update(completed_extra)
        await emit("node_completed", **completed_kwargs)
        return result, selected, pruned

    while ready:
        if abort_event is not None and abort_event.is_set():
            await emit("run_aborted")
            return

        nid = min(ready, key=lambda x: (ranks.get(x, len(ranks)), x))
        ready.discard(nid)
        if nid in done:
            continue

        node = nodes_by_id.get(nid)
        if node is None:
            await emit("run_failed", error=f"node {nid!r} not found in workflow")
            return

        try:
            _result, selected, pruned = await _execute(node)
        except _RunFailed as exc:
            await emit("run_failed", error=str(exc))
            return
        except executor._RunRejected:
            return
        except executor._RunAborted:
            await emit("run_aborted")
            return

        done.add(nid)

        if abort_event is not None and abort_event.is_set():
            await emit("run_aborted")
            return

        for e in pruned:
            edge_state[e.id] = "pruned"
            await emit("branch_pruned", node_id=nid, edge_id=e.id)
        for e in selected:
            edge_state[e.id] = "selected"
        for e in outgoing.get(nid, []):
            await _resolve_edge(e)

    if had_tolerated_failure:
        await emit(
            "run_completed_with_errors",
            failed_node_count=len(failed_node_ids),
            failed_node_ids=failed_node_ids,
        )
    else:
        await emit("run_completed")


__all__ = ["execute_dag", "SwitchNoMatch"]
