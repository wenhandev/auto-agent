"""A bounded, whitelisted expression evaluator for ``{{= <expr> }}`` tokens.

Expressions are parsed with :func:`ast.parse(mode="eval")` and interpreted by a
manual recursive walker over a node-type allowlist. We never call
``eval``/``exec``/``compile``. Safety rests on three deny-by-default layers:

1. a node-type allowlist (rejects lambda, walrus, assignment, imports, ...),
2. an attribute allowlist with a hard dunder ban, and
3. a call allowlist (only :data:`SAFE_FUNCTIONS` / per-type methods).

Length, AST-size, iteration, and wall-clock caps bound every evaluation.
"""
from __future__ import annotations

import ast
import json
import string
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from app.settings import settings

_AVAILABLE_NAMES = "nodes, item, items, params, now"


class ExpressionError(ValueError):
    pass


# --- node-type allowlist --------------------------------------------------

_ALLOWED_NODES: tuple[type, ...] = (
    ast.Expression, ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.IfExp,
    ast.Compare, ast.Call, ast.Constant, ast.List, ast.Tuple, ast.Dict,
    ast.Set, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
    ast.comprehension, ast.Name, ast.Load, ast.Store, ast.Subscript, ast.Slice,
    ast.Attribute, ast.And, ast.Or, ast.Not, ast.Add, ast.Sub, ast.Mult,
    ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd, ast.Eq,
    ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
    ast.keyword, ast.Starred,
)
# ``ast.Index`` exists on <=3.8 only; include it when present for safety.
if hasattr(ast, "Index"):  # pragma: no cover - version dependent
    _ALLOWED_NODES = _ALLOWED_NODES + (ast.Index,)


# --- attribute allowlists -------------------------------------------------

_STR_METHODS = frozenset({
    "upper", "lower", "strip", "lstrip", "rstrip", "replace", "split",
    "rsplit", "startswith", "endswith", "title", "zfill", "format",
})
_DICT_METHODS = frozenset({"get"})


# --- datetime helpers -----------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_date(value: Any, fmt: str | None = None) -> datetime:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ExpressionError("parse_date expects a string")
    if fmt is not None:
        return datetime.strptime(value, fmt)
    return datetime.fromisoformat(value)


def _format_date(value: Any, fmt: str) -> str:
    if not isinstance(value, datetime):
        value = _parse_date(value)
    return value.strftime(fmt)


def _date_add(
    value: Any,
    days: float = 0,
    seconds: float = 0,
    minutes: float = 0,
    hours: float = 0,
    weeks: float = 0,
) -> datetime:
    if not isinstance(value, datetime):
        value = _parse_date(value)
    return value + timedelta(
        days=days, seconds=seconds, minutes=minutes, hours=hours, weeks=weeks
    )


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


# Functions that need no per-evaluation state.
_STATIC_FUNCTIONS: dict[str, Any] = {
    "len": len, "str": str, "int": int, "float": float, "bool": bool,
    "round": round, "abs": abs, "min": min, "max": max, "sum": sum,
    "sorted": sorted, "any": any, "all": all, "enumerate": enumerate,
    "zip": zip, "json_parse": json.loads, "json_stringify": _json_dumps,
    "now": _now, "parse_date": _parse_date, "format_date": _format_date,
    "date_add": _date_add,
}


class _Interpreter:
    def __init__(self, expr: str, namespace: dict[str, Any]) -> None:
        self.expr = expr
        self.namespace = namespace
        self.max_iter = int(settings.expr_max_iter)
        self.iter_count = 0
        self.deadline = time.monotonic() + (int(settings.expr_timeout_ms) / 1000.0)
        # Per-instance functions whose iteration is bounded by this run.
        self.functions: dict[str, Any] = dict(_STATIC_FUNCTIONS)
        self.functions["range"] = self._bounded_range
        self.functions["map"] = self._bounded_map
        self.functions["filter"] = self._bounded_filter

    # -- limits ------------------------------------------------------------

    def _tick(self) -> None:
        if time.monotonic() > self.deadline:
            raise ExpressionError(
                f"wall-clock cap of {settings.expr_timeout_ms}ms exceeded"
            )

    def _count(self, n: int = 1) -> None:
        self.iter_count += n
        if self.iter_count > self.max_iter:
            raise ExpressionError(
                f"iteration cap of {self.max_iter} elements exceeded"
            )

    def _bounded_range(self, *args: Any) -> range:
        r = range(*args)
        if len(r) > self.max_iter:
            raise ExpressionError(
                f"iteration cap of {self.max_iter} elements exceeded"
            )
        return r

    def _bounded_map(self, func: Any, *iterables: Any) -> list:
        out = []
        for values in zip(*iterables):
            self._count()
            self._tick()
            out.append(func(*values))
        return out

    def _bounded_filter(self, func: Any, iterable: Any) -> list:
        out = []
        for value in iterable:
            self._count()
            self._tick()
            keep = bool(value) if func is None else bool(func(value))
            if keep:
                out.append(value)
        return out

    # -- attribute resolution ---------------------------------------------

    def _get_attr(self, obj: Any, name: str) -> Any:
        if name.startswith("_") or name.endswith("_"):
            raise ExpressionError(
                f"attribute {name!r} is not accessible (dunder/private access banned)"
            )
        if isinstance(obj, NodeResult):
            if name == "output":
                return obj.output
            if name == "items":
                return [it.json for it in obj.items]
            if name == "item":
                return obj.items[0].json if obj.items else {}
            raise ExpressionError(
                f"attribute {name!r} is not available on a node result"
            )
        if isinstance(obj, Item):
            if name == "json":
                return obj.json
            if name == "binary":
                return obj.binary_summary()
            raise ExpressionError(
                f"attribute {name!r} is not available on an item"
            )
        if isinstance(obj, dict):
            if name in obj:
                return obj[name]
            if name in _DICT_METHODS:
                return getattr(obj, name)
            raise ExpressionError(f"key {name!r} not found")
        if isinstance(obj, str):
            if name in _STR_METHODS:
                if name == "format":
                    return self._safe_format(obj)
                return getattr(obj, name)
            raise ExpressionError(
                f"string method {name!r} is not available"
            )
        raise ExpressionError(
            f"attribute access on {type(obj).__name__} is not allowed"
        )

    def _safe_format(self, template: str) -> Any:
        def _format(*args: Any, **kwargs: Any) -> str:
            for _, field_name, _, _ in string.Formatter().parse(template):
                if field_name and ("." in field_name or "[" in field_name):
                    raise ExpressionError(
                        "str.format with attribute/index field access is not allowed"
                    )
            return template.format(*args, **kwargs)

        return _format

    # -- evaluation --------------------------------------------------------

    def eval(self, node: ast.AST, env: dict[str, Any]) -> Any:
        self._tick()
        method = getattr(self, "_eval_" + type(node).__name__, None)
        if method is None:
            raise ExpressionError(
                f"syntax element {type(node).__name__!r} is not allowed"
            )
        return method(node, env)

    def _eval_Expression(self, node: ast.Expression, env: dict[str, Any]) -> Any:
        return self.eval(node.body, env)

    def _eval_Constant(self, node: ast.Constant, env: dict[str, Any]) -> Any:
        return node.value

    def _eval_Name(self, node: ast.Name, env: dict[str, Any]) -> Any:
        if node.id in env:
            return env[node.id]
        if node.id in self.namespace:
            return self.namespace[node.id]
        raise ExpressionError(
            f"name {node.id!r} is not defined; available names: {_AVAILABLE_NAMES}"
        )

    def _eval_List(self, node: ast.List, env: dict[str, Any]) -> Any:
        return [self._eval_elt(e, env) for e in node.elts]

    def _eval_Tuple(self, node: ast.Tuple, env: dict[str, Any]) -> Any:
        return tuple(self._eval_elt(e, env) for e in node.elts)

    def _eval_Set(self, node: ast.Set, env: dict[str, Any]) -> Any:
        return set(self._eval_elt(e, env) for e in node.elts)

    def _eval_elt(self, node: ast.AST, env: dict[str, Any]) -> Any:
        if isinstance(node, ast.Starred):
            return self.eval(node.value, env)  # handled by caller via expansion
        return self.eval(node, env)

    def _eval_Dict(self, node: ast.Dict, env: dict[str, Any]) -> Any:
        out: dict[Any, Any] = {}
        for k, v in zip(node.keys, node.values):
            if k is None:
                merged = self.eval(v, env)
                if not isinstance(merged, dict):
                    raise ExpressionError("dict unpacking requires a mapping")
                out.update(merged)
            else:
                out[self.eval(k, env)] = self.eval(v, env)
        return out

    def _eval_BoolOp(self, node: ast.BoolOp, env: dict[str, Any]) -> Any:
        if isinstance(node.op, ast.And):
            result: Any = True
            for value in node.values:
                result = self.eval(value, env)
                if not result:
                    return result
            return result
        result = False
        for value in node.values:
            result = self.eval(value, env)
            if result:
                return result
        return result

    def _eval_UnaryOp(self, node: ast.UnaryOp, env: dict[str, Any]) -> Any:
        operand = self.eval(node.operand, env)
        if isinstance(node.op, ast.Not):
            return not operand
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return +operand
        raise ExpressionError("unary operator not allowed")

    _BINOPS = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b,
        ast.FloorDiv: lambda a, b: a // b,
        ast.Mod: lambda a, b: a % b,
        ast.Pow: lambda a, b: a ** b,
    }

    def _eval_BinOp(self, node: ast.BinOp, env: dict[str, Any]) -> Any:
        op = self._BINOPS.get(type(node.op))
        if op is None:
            raise ExpressionError("binary operator not allowed")
        left = self.eval(node.left, env)
        right = self.eval(node.right, env)
        if isinstance(node.op, ast.Pow):
            # Guard against accidental enormous exponentiation.
            if isinstance(right, (int, float)) and right > 1000:
                raise ExpressionError("exponent too large")
        return op(left, right)

    _CMPOPS = {
        ast.Eq: lambda a, b: a == b,
        ast.NotEq: lambda a, b: a != b,
        ast.Lt: lambda a, b: a < b,
        ast.LtE: lambda a, b: a <= b,
        ast.Gt: lambda a, b: a > b,
        ast.GtE: lambda a, b: a >= b,
        ast.In: lambda a, b: a in b,
        ast.NotIn: lambda a, b: a not in b,
    }

    def _eval_Compare(self, node: ast.Compare, env: dict[str, Any]) -> Any:
        left = self.eval(node.left, env)
        for op, comparator in zip(node.ops, node.comparators):
            fn = self._CMPOPS.get(type(op))
            if fn is None:
                raise ExpressionError("comparison operator not allowed")
            right = self.eval(comparator, env)
            if not fn(left, right):
                return False
            left = right
        return True

    def _eval_IfExp(self, node: ast.IfExp, env: dict[str, Any]) -> Any:
        if self.eval(node.test, env):
            return self.eval(node.body, env)
        return self.eval(node.orelse, env)

    def _eval_Attribute(self, node: ast.Attribute, env: dict[str, Any]) -> Any:
        obj = self.eval(node.value, env)
        return self._get_attr(obj, node.attr)

    def _eval_Subscript(self, node: ast.Subscript, env: dict[str, Any]) -> Any:
        obj = self.eval(node.value, env)
        sl = node.slice
        if hasattr(ast, "Index") and isinstance(sl, getattr(ast, "Index")):
            sl = sl.value  # type: ignore[attr-defined]
        if isinstance(sl, ast.Slice):
            lower = self.eval(sl.lower, env) if sl.lower else None
            upper = self.eval(sl.upper, env) if sl.upper else None
            step = self.eval(sl.step, env) if sl.step else None
            return obj[slice(lower, upper, step)]
        key = self.eval(sl, env)
        return obj[key]

    def _eval_args(self, node: ast.Call, env: dict[str, Any]) -> tuple[list, dict]:
        args: list[Any] = []
        for a in node.args:
            if isinstance(a, ast.Starred):
                args.extend(self.eval(a.value, env))
            else:
                args.append(self.eval(a, env))
        kwargs: dict[str, Any] = {}
        for kw in node.keywords:
            if kw.arg is None:
                mapping = self.eval(kw.value, env)
                if not isinstance(mapping, dict):
                    raise ExpressionError("keyword unpacking requires a mapping")
                kwargs.update(mapping)
            else:
                kwargs[kw.arg] = self.eval(kw.value, env)
        return args, kwargs

    def _eval_Call(self, node: ast.Call, env: dict[str, Any]) -> Any:
        func_node = node.func
        if isinstance(func_node, ast.Name):
            name = func_node.id
            if name in env:
                raise ExpressionError(f"function {name!r} is not available")
            if name not in self.functions:
                raise ExpressionError(f"function {name!r} is not available")
            func = self.functions[name]
        elif isinstance(func_node, ast.Attribute):
            func = self.eval(func_node, env)
            if not callable(func):
                raise ExpressionError(
                    f"attribute {func_node.attr!r} is not callable"
                )
        else:
            raise ExpressionError("call target is not allowed")
        args, kwargs = self._eval_args(node, env)
        return func(*args, **kwargs)

    # -- comprehensions ----------------------------------------------------

    def _bind_target(self, target: ast.AST, value: Any, env: dict[str, Any]) -> None:
        if isinstance(target, ast.Name):
            env[target.id] = value
        elif isinstance(target, ast.Tuple):
            values = list(value)
            if len(values) != len(target.elts):
                raise ExpressionError("comprehension unpacking length mismatch")
            for t, v in zip(target.elts, values):
                self._bind_target(t, v, env)
        else:
            raise ExpressionError("comprehension target is not allowed")

    def _iter_comprehension(
        self,
        generators: list[ast.comprehension],
        index: int,
        env: dict[str, Any],
        emit,
    ) -> None:
        if index >= len(generators):
            emit(env)
            return
        gen = generators[index]
        iterable = self.eval(gen.iter, env)
        for value in iterable:
            self._count()
            self._tick()
            local = dict(env)
            self._bind_target(gen.target, value, local)
            if all(self.eval(cond, local) for cond in gen.ifs):
                self._iter_comprehension(generators, index + 1, local, emit)

    def _eval_ListComp(self, node: ast.ListComp, env: dict[str, Any]) -> Any:
        out: list[Any] = []
        self._iter_comprehension(
            node.generators, 0, env, lambda e: out.append(self.eval(node.elt, e))
        )
        return out

    def _eval_SetComp(self, node: ast.SetComp, env: dict[str, Any]) -> Any:
        out: set[Any] = set()
        self._iter_comprehension(
            node.generators, 0, env, lambda e: out.add(self.eval(node.elt, e))
        )
        return out

    def _eval_GeneratorExp(self, node: ast.GeneratorExp, env: dict[str, Any]) -> Any:
        out: list[Any] = []
        self._iter_comprehension(
            node.generators, 0, env, lambda e: out.append(self.eval(node.elt, e))
        )
        return iter(out)

    def _eval_DictComp(self, node: ast.DictComp, env: dict[str, Any]) -> Any:
        out: dict[Any, Any] = {}

        def emit(e: dict[str, Any]) -> None:
            out[self.eval(node.key, e)] = self.eval(node.value, e)

        self._iter_comprehension(node.generators, 0, env, emit)
        return out


def _check_whitelist(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ExpressionError(
                f"syntax element {type(node).__name__!r} is not allowed"
            )


def _sanitise_cause(exc: Exception) -> str:
    if isinstance(exc, ExpressionError):
        return str(exc)
    if isinstance(exc, ZeroDivisionError):
        return "division by zero"
    if isinstance(exc, KeyError):
        return f"key {exc.args[0]!r} not found" if exc.args else "key not found"
    if isinstance(exc, IndexError):
        return "index out of range"
    if isinstance(exc, (TypeError, ValueError, AttributeError, NameError)):
        return f"{type(exc).__name__}: {exc}"
    return type(exc).__name__


def evaluate(expr: str, namespace: dict[str, Any]) -> Any:
    """Evaluate ``expr`` against ``namespace`` under the safety allowlists."""
    try:
        if not isinstance(expr, str):
            raise ExpressionError("expression must be a string")
        max_len = int(settings.expr_max_len)
        if len(expr) > max_len:
            raise ExpressionError(
                f"source length cap of {max_len} characters exceeded"
            )
        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as exc:
            raise ExpressionError(f"syntax error: {exc.msg}") from exc

        _check_whitelist(tree)

        max_nodes = int(settings.expr_max_nodes)
        node_count = sum(1 for _ in ast.walk(tree))
        if node_count > max_nodes:
            raise ExpressionError(
                f"AST node cap of {max_nodes} nodes exceeded"
            )

        ns = dict(namespace)
        ns.setdefault("params", {})
        ns.setdefault("now", _now())
        ns.setdefault("nodes", {})

        return _Interpreter(expr, ns).eval(tree, {})
    except Exception as exc:  # re-wrap with the documented error contract
        cause = _sanitise_cause(exc)
        truncated = expr[:120] if isinstance(expr, str) else str(type(expr))
        raise ExpressionError(
            f"expression failed: {truncated}; {cause}; "
            f"available names: {_AVAILABLE_NAMES}"
        ) from exc


# Imported lazily by ``app.nodes.result`` consumers; import here so attribute
# checks against NodeResult/Item are robust.
from app.nodes.result import Item, NodeResult  # noqa: E402

# Self-register with the interpolation seam at import time.
from app.services.variable_interpolation import (  # noqa: E402
    register_expression_evaluator,
)

register_expression_evaluator(evaluate)


__all__ = ["ExpressionError", "evaluate"]
