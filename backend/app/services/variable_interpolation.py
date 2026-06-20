"""Chained variable interpolation for node params.

Resolves, in a single non-recursive tree walk, the token families:

- ``{{params.<name>[.path]}}``       — workflow input parameters (run-scoped)
- ``{{nodes.<id>.output[.path]}}``  — a predecessor node's output dict
- ``{{nodes.<id>.items}}``          — the predecessor's items (summarised)
- ``{{nodes.<id>.item.json[.path]}}`` — sugar for ``items[0].json``
- ``{{cred.<name>.<field>}}``       — the credential vault (existing)
- ``{{totp.<name>}}``               — live TOTP code (RFC 6238)
- ``{{card.<name>.<field>}}``       — credit-card field at fill time
- ``{{= <expr> }}``                 — a safe expression (expression-engine)

Whole-token values preserve type; interpolated tokens stringify. Missing
paths and unknown prefixes raise :class:`VariableResolutionError`. The
prefixes ``run`` / ``trigger`` are reserved for a future change.
"""
from __future__ import annotations

import difflib
import json
import re
from typing import Any, Callable, Optional

from sqlmodel import Session

from app.nodes.result import BinaryRef, Item, NodeResult
from app.services import artifact_context
from app.services import credential_interpolation


class VariableResolutionError(ValueError):
    pass


# {{ ... }} — inner captured non-greedily; tokens do not nest.
_TOKEN_RE = re.compile(r"\{\{\s*(?P<inner>.+?)\s*\}\}", re.DOTALL)

_RESERVED_PREFIXES = ("run", "trigger")
_SUPPORTED_PREFIXES = "params, nodes, cred, totp, card, run, trigger"


# --- Expression-engine seam ----------------------------------------------
# The expression-engine change registers an evaluator here. Until then a
# `{{= ... }}` token raises a clear error.
_EXPRESSION_EVALUATOR: Optional[Callable[[str, dict[str, Any]], Any]] = None


def register_expression_evaluator(fn: Callable[[str, dict[str, Any]], Any]) -> None:
    global _EXPRESSION_EVALUATOR
    _EXPRESSION_EVALUATOR = fn


# --- path helpers ---------------------------------------------------------

def _available_paths(obj: Any, prefix: str, *, limit: int = 8) -> list[str]:
    out: list[str] = []

    def walk(o: Any, pfx: str) -> None:
        if len(out) >= limit:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                p = f"{pfx}.{k}"
                out.append(p)
                if len(out) >= limit:
                    return
                walk(v, p)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                p = f"{pfx}.{i}"
                out.append(p)
                if len(out) >= limit:
                    return
                walk(v, p)

    walk(obj, prefix)
    return out[:limit]


def _navigate(base: Any, segments: list[str], *, full_label: str, node_id: str) -> Any:
    cur = base
    walked = full_label
    for seg in segments:
        if isinstance(cur, list):
            try:
                idx = int(seg)
                cur = cur[idx]
            except (ValueError, IndexError):
                _raise_missing(base, full_label, walked, seg, node_id)
        elif isinstance(cur, dict):
            if seg not in cur:
                _raise_missing(base, full_label, walked, seg, node_id)
            cur = cur[seg]
        else:
            _raise_missing(base, full_label, walked, seg, node_id)
        walked = f"{walked}.{seg}"
    return cur


def _raise_missing(base: Any, full_label: str, walked: str, seg: str, node_id: str) -> None:
    failed = f"{walked}.{seg}"
    available = _available_paths(base, full_label.split(".")[0])
    suggestion = ""
    close = difflib.get_close_matches(failed, available, n=1, cutoff=0.6)
    if close:
        suggestion = f"; did you mean {close[0]!r}?"
    raise VariableResolutionError(
        f"path {failed!r} missing on node {node_id!r}{suggestion}; "
        f"available paths: {available}"
    )


# --- params token resolution ------------------------------------------------

def _resolve_params_token(inner: str, params_namespace: dict[str, Any]) -> Any:
    parts = inner.split(".")
    if len(parts) < 2:
        raise VariableResolutionError(f"malformed params token '{{{{{inner}}}}}'")
    name = parts[1]
    rest = parts[2:]
    if name not in params_namespace:
        available = ", ".join(sorted(params_namespace.keys())) or "(none)"
        raise VariableResolutionError(
            f"parameter {name!r} is not set (available: {available})"
        )
    base = params_namespace[name]
    if not rest:
        return base
    return _navigate(base, rest, full_label=f"params.{name}", node_id="params")


# --- node token resolution ------------------------------------------------

def _resolve_node_token(inner: str, context: dict[str, NodeResult]) -> Any:
    # inner == "nodes.<id>.<root>[.path]"
    parts = inner.split(".")
    # parts[0] == "nodes"
    if len(parts) < 2:
        raise VariableResolutionError(f"malformed node token '{{{{{inner}}}}}'")
    node_id = parts[1]
    if node_id not in context:
        available = ", ".join(sorted(context.keys())) or "(none)"
        raise VariableResolutionError(
            f"node {node_id!r} has not run yet (available: {available})"
        )
    result = context[node_id]
    if len(parts) == 2:
        # bare {{nodes.<id>}} -> the output dict
        return result.output
    root = parts[2]
    rest = parts[3:]
    if root == "output":
        return _navigate(result.output, rest, full_label="output", node_id=node_id)
    if root == "items":
        return _navigate(result.items_summary(), rest, full_label="items", node_id=node_id)
    if root == "item":
        first = result.items[0] if result.items else Item(json={})
        if not rest:
            return first.json
        sub = rest[0]
        if sub == "json":
            return _navigate(first.json, rest[1:], full_label="item.json", node_id=node_id)
        if sub == "binary":
            raise VariableResolutionError(
                "binary values cannot be interpolated into text; "
                "use a file node to consume binary"
            )
        raise VariableResolutionError(
            f"unknown item field {sub!r}; use 'item.json' or 'item.binary'"
        )
    raise VariableResolutionError(
        f"unknown root {root!r} for node {node_id!r}; use 'output', 'items', or 'item'"
    )


# --- run / trigger token resolution -------------------------------------

def _resolve_run_token(inner: str, namespace: dict[str, Any]) -> Any:
    parts = inner.split(".")
    if len(parts) < 2:
        raise VariableResolutionError(f"malformed run token '{{{{{inner}}}}}'")
    root = parts[1]
    rest = parts[2:]
    if root == "context":
        base = namespace.get("context") or {}
        return _navigate(base, rest, full_label="run.context", node_id="run")
    if root == "input":
        base = namespace.get("input") or namespace.get("body") or {}
        return _navigate(base, rest, full_label="run.input", node_id="run")
    raise VariableResolutionError(
        f"unknown run root {root!r}; use 'context' or 'input'"
    )


def _resolve_trigger_token(inner: str, namespace: dict[str, Any]) -> Any:
    parts = inner.split(".")
    if len(parts) < 2:
        raise VariableResolutionError(f"malformed trigger token '{{{{{inner}}}}}'")
    root = parts[1]
    rest = parts[2:]
    if root == "headers":
        base = namespace.get("headers") or {}
        return _navigate(base, rest, full_label="trigger.headers", node_id="trigger")
    if not rest:
        if root not in namespace:
            raise VariableResolutionError(
                f"trigger field {root!r} missing; available: "
                f"{sorted(k for k in namespace.keys() if k != 'context')}"
            )
        return namespace[root]
    base = namespace.get(root)
    if base is None:
        raise VariableResolutionError(f"trigger field {root!r} missing")
    if isinstance(base, dict):
        return _navigate(base, rest, full_label=f"trigger.{root}", node_id="trigger")
    raise VariableResolutionError(f"trigger field {root!r} is not an object")


# --- token dispatch -------------------------------------------------------

def _resolve_token(
    inner: str,
    *,
    context: dict[str, NodeResult],
    cred_resolver: Optional[Callable[[str, str], str]],
    totp_resolver: Optional[Callable[[str], str]],
    card_resolver: Optional[Callable[[str, str], str]],
    namespace_builder: Optional[Callable[[], dict[str, Any]]],
    trigger_namespace: Optional[dict[str, Any]] = None,
    params_namespace: Optional[dict[str, Any]] = None,
    resolve_expressions: bool = True,
) -> Any:
    inner = inner.strip()
    if inner.startswith("="):
        if not resolve_expressions:
            return f"{{{{= {inner[1:].strip()} }}}}"
        if _EXPRESSION_EVALUATOR is None:
            # Lazy-load the expression engine; it self-registers on import.
            try:
                import app.services.expressions  # noqa: F401
            except Exception:
                pass
        if _EXPRESSION_EVALUATOR is None:
            raise VariableResolutionError(
                "expression engine is not enabled; '{{= ... }}' tokens are unavailable"
            )
        namespace = namespace_builder() if namespace_builder else {}
        return _EXPRESSION_EVALUATOR(inner[1:].strip(), namespace)

    prefix = inner.split(".", 1)[0]
    if prefix == "params":
        if params_namespace is None:
            raise VariableResolutionError(
                "parameter resolution requires a run parameter context"
            )
        return _resolve_params_token(inner, params_namespace)
    if prefix == "nodes":
        return _resolve_node_token(inner, context)
    if prefix == "cred":
        if cred_resolver is None:
            raise VariableResolutionError(
                "credential resolution requires a database session"
            )
        cred_parts = inner.split(".")
        if len(cred_parts) != 3:
            raise VariableResolutionError(
                f"malformed credential token '{{{{{inner}}}}}'; "
                "expected {{cred.<name>.<field>}} or {{cred.<mount>:<name>.<field>}}"
            )
        middle = cred_parts[1]
        field = cred_parts[2]
        resolve_middle = getattr(cred_resolver, "resolve_token_middle", None)
        if callable(resolve_middle):
            resolved = resolve_middle(middle, field)
        elif ":" in middle:
            mount, name = middle.split(":", 1)
            resolved = cred_resolver(mount, name, field)
        else:
            resolved = cred_resolver(middle, field)
        artifact_context.register_sensitive(field, str(resolved))
        return resolved
    if prefix == "totp":
        if totp_resolver is None:
            raise VariableResolutionError(
                "TOTP resolution requires a database session"
            )
        totp_parts = inner.split(".")
        if len(totp_parts) != 2:
            raise VariableResolutionError(
                f"malformed TOTP token '{{{{{inner}}}}}'; "
                "expected {{totp.<name>}}"
            )
        code = totp_resolver(totp_parts[1])
        artifact_context.register_sensitive("totp_code", str(code), credential_type="totp")
        return code
    if prefix == "card":
        if card_resolver is None:
            raise VariableResolutionError(
                "card resolution requires a database session"
            )
        card_parts = inner.split(".")
        if len(card_parts) != 3:
            raise VariableResolutionError(
                f"malformed card token '{{{{{inner}}}}}'; "
                "expected {{card.<name>.<field>}}"
            )
        field = card_parts[2]
        resolved = card_resolver(card_parts[1], field)
        artifact_context.register_sensitive(
            field,
            str(resolved),
            credential_type="credit_card",
        )
        return resolved
    if prefix == "run":
        if trigger_namespace is None:
            raise VariableResolutionError(
                f"prefix {prefix!r} is reserved for a future change"
            )
        return _resolve_run_token(inner, trigger_namespace)
    if prefix == "trigger":
        if trigger_namespace is None:
            raise VariableResolutionError(
                f"prefix {prefix!r} is reserved for a future change"
            )
        return _resolve_trigger_token(inner, trigger_namespace)
    if prefix in _RESERVED_PREFIXES:
        raise VariableResolutionError(
            f"prefix {prefix!r} is reserved for a future change"
        )
    raise VariableResolutionError(
        f"unknown variable prefix {prefix!r} in '{{{{{inner}}}}}'; "
        f"supported prefixes: {_SUPPORTED_PREFIXES}"
    )


def _stringify(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, BinaryRef):
        raise VariableResolutionError(
            "binary values cannot be interpolated into text; "
            "use a file node to consume binary"
        )
    return str(value)


def _substitute_in_string(text: str, **kw: Any) -> Any:
    matches = list(_TOKEN_RE.finditer(text))
    if not matches:
        return text
    # whole-token: the entire string is exactly one token -> preserve type
    if len(matches) == 1 and matches[0].group(0).strip() == text.strip():
        resolved = _resolve_token(matches[0].group("inner"), **kw)
        if kw.get("resolve_expressions") is False and isinstance(resolved, str):
            return text
        return resolved

    def repl(m: re.Match[str]) -> str:
        return _stringify(_resolve_token(m.group("inner"), **kw))

    return _TOKEN_RE.sub(repl, text)


def _walk(value: Any, **kw: Any) -> Any:
    if isinstance(value, str):
        return _substitute_in_string(value, **kw)
    if isinstance(value, list):
        return [_walk(v, **kw) for v in value]
    if isinstance(value, dict):
        return {k: _walk(v, **kw) for k, v in value.items()}
    return value


def resolve_params(
    params: dict[str, Any],
    *,
    context: Optional[dict[str, NodeResult]] = None,
    session: Optional[Session] = None,
    workflow_id: Optional[str] = None,
    input_items: Optional[list[Item]] = None,
    trigger_namespace: Optional[dict[str, Any]] = None,
    params_namespace: Optional[dict[str, Any]] = None,
    resolve_expressions: bool = True,
) -> dict[str, Any]:
    """Resolve all ``{{...}}`` tokens in ``params`` in one tree walk."""
    context = context or {}
    params_namespace = params_namespace or {}
    cred_resolver: Optional[Callable[[str, str], str]] = None
    totp_resolver: Optional[Callable[[str], str]] = None
    card_resolver: Optional[Callable[[str, str], str]] = None
    if session is not None:
        cred_resolver = credential_interpolation.make_token_resolver(
            session, workflow_id=workflow_id
        )

        def _totp(name: str) -> str:
            from app.services.totp import resolve_totp_code

            return resolve_totp_code(
                name, session, workflow_id=workflow_id, refresh_if_stale=False
            )

        def _card(name: str, field: str) -> str:
            from app.services.totp import resolve_card_field

            return resolve_card_field(
                name, field, session, workflow_id=workflow_id
            )

        totp_resolver = _totp
        card_resolver = _card

    def namespace_builder() -> dict[str, Any]:
        items = input_items or []
        ns: dict[str, Any] = {
            "params": params_namespace,
            "nodes": context,
            "item": (items[0].json if items else {}),
            "items": [it.json for it in items],
            "input_items": items,
        }
        if trigger_namespace is not None:
            ns["run"] = trigger_namespace.get("context") or {}
            ns["trigger"] = {
                k: v for k, v in trigger_namespace.items() if k != "context"
            }
        return ns

    return _walk(
        params,
        context=context,
        cred_resolver=cred_resolver,
        totp_resolver=totp_resolver,
        card_resolver=card_resolver,
        namespace_builder=namespace_builder,
        trigger_namespace=trigger_namespace,
        params_namespace=params_namespace,
        resolve_expressions=resolve_expressions,
    )


__all__ = [
    "resolve_params",
    "register_expression_evaluator",
    "VariableResolutionError",
]
