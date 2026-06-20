from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.expressions import ExpressionError, evaluate


def _ns() -> dict:
    return {"nodes": {}, "item": {}, "items": [], "input_items": []}


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os')",
        "().__class__",
        "[].__class__.__mro__",
        "''.__class__.__bases__",
        "(1).__class__",
        "getattr([], 'append')",
        "open('/x')",
        "eval('1')",
        "(lambda: 1)()",
        "(x := 1)",
        "'{0.__class__}'.format(1)",
    ],
)
def test_sandbox_escapes_rejected(expr: str):
    with pytest.raises(ExpressionError):
        evaluate(expr, _ns())


def test_dangerous_builtin_message():
    with pytest.raises(ExpressionError) as ei:
        evaluate("open('/x')", _ns())
    assert "is not available" in str(ei.value)


def test_dunder_attribute_does_not_leak_class():
    with pytest.raises(ExpressionError):
        evaluate("''.__class__", _ns())


def test_length_cap_breach():
    expr = "1+" * 1100 + "1"  # > 2048 chars
    assert len(expr) > 2048
    with pytest.raises(ExpressionError) as ei:
        evaluate(expr, _ns())
    assert "length cap" in str(ei.value)


def test_iteration_cap_breach():
    with pytest.raises(ExpressionError) as ei:
        evaluate("[x for x in range(100000)]", _ns())
    assert "iteration cap" in str(ei.value)


def test_oversized_nested_comprehension():
    with pytest.raises(ExpressionError) as ei:
        evaluate("[[y for y in range(1000)] for x in range(1000)]", _ns())
    assert "iteration cap" in str(ei.value) or "ms exceeded" in str(ei.value)


def test_walrus_rejected_before_eval():
    with pytest.raises(ExpressionError):
        evaluate("(x := 1)", _ns())


def test_error_lists_available_names():
    with pytest.raises(ExpressionError) as ei:
        evaluate("secrets.key", _ns())
    msg = str(ei.value)
    assert "available names: nodes, item, items, params, now" in msg
