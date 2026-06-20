"""Typed predicate evaluation for validation and while_loop nodes."""
from __future__ import annotations

from typing import Any


class PredicateError(ValueError):
    pass


def evaluate_predicate(left: Any, op: str, right: Any = None) -> bool:
    """Evaluate a :class:`~app.schemas.ConditionPredicate` operator."""
    if op == "is_truthy":
        return bool(left)
    if op == "is_falsy":
        return not bool(left)
    if op == "in":
        if right is None:
            raise PredicateError("operator 'in' requires right operand")
        try:
            return left in right
        except TypeError as exc:
            raise PredicateError(f"operator 'in' failed: {exc}") from exc
    if op == "not_in":
        if right is None:
            raise PredicateError("operator 'not_in' requires right operand")
        try:
            return left not in right
        except TypeError as exc:
            raise PredicateError(f"operator 'not_in' failed: {exc}") from exc

    if right is None:
        raise PredicateError(f"operator {op!r} requires right operand")

    try:
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
    except TypeError as exc:
        raise PredicateError(f"comparison {op!r} failed: {exc}") from exc

    raise PredicateError(f"unsupported predicate operator: {op!r}")


__all__ = ["PredicateError", "evaluate_predicate"]
