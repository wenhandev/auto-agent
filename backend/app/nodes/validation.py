from __future__ import annotations

from typing import Any

from app.nodes._helpers import build_namespace, eval_value
from app.nodes.result import Item
from app.services.predicate import PredicateError, evaluate_predicate


async def run(
    params: dict[str, Any],
    *,
    input_items: list[Item],
    context: dict[str, Any],
) -> list[Item]:
    pred = params.get("predicate")
    if not isinstance(pred, dict):
        raise ValueError("validation requires predicate object")

    ns = build_namespace(
        input_items[0] if input_items else Item(json={}),
        input_items,
        context,
    )
    left = eval_value(pred.get("left"), ns)
    op = str(pred.get("op", "=="))
    right = eval_value(pred.get("right"), ns) if "right" in pred else pred.get("right")

    try:
        passed = evaluate_predicate(left, op, right)
    except PredicateError as exc:
        raise ValueError(str(exc)) from exc

    checked = {"left": left, "op": op, "right": right}
    out: dict[str, Any] = {"passed": passed, "checked": checked}
    if not passed:
        out["reason"] = f"predicate failed: {left!r} {op} {right!r}"
    return [Item(json=out)]
