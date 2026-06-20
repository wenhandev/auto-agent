from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.nodes.result import Item, NodeResult
from app.services.expressions import evaluate


def _ns(**kw) -> dict:
    base = {"nodes": {}, "item": {}, "items": [], "input_items": []}
    base.update(kw)
    return base


def test_arithmetic():
    assert evaluate("2+3*4", _ns()) == 14


def test_comparison():
    assert evaluate("3 > 2", _ns()) is True
    assert evaluate("1 < 2 <= 2 < 3", _ns()) is True
    assert evaluate("5 in [1, 5, 9]", _ns()) is True


def test_boolean():
    assert evaluate("True and False", _ns()) is False
    assert evaluate("False or 7", _ns()) == 7
    assert evaluate("not 0", _ns()) is True


def test_conditional():
    assert evaluate("'yes' if 1 else 'no'", _ns()) == "yes"
    assert evaluate("'yes' if 0 else 'no'", _ns()) == "no"


def test_subscript_and_slice():
    assert evaluate("[1, 2, 3][1]", _ns()) == 2
    assert evaluate("[1, 2, 3, 4][1:3]", _ns()) == [2, 3]
    assert evaluate("{'a': 1}['a']", _ns()) == 1


def test_list_comprehension_with_filter():
    ns = _ns(items=[0, 1, 2, 0, 3])
    assert evaluate("[i for i in items if i]", ns) == [1, 2, 3]


def test_dict_comprehension():
    ns = _ns(items=[1, 2, 3])
    assert evaluate("{i: i * i for i in items}", ns) == {1: 1, 2: 4, 3: 9}


def test_allowed_builtins():
    ns = _ns(items=[3, 1, 2])
    assert evaluate("len(items)", ns) == 3
    assert evaluate("sum(items)", ns) == 6
    assert evaluate("sorted(items)", ns) == [1, 2, 3]
    assert evaluate("min(items)", ns) == 1
    assert evaluate("max(items)", ns) == 3


def test_string_methods():
    assert evaluate("'abc'.upper()", _ns()) == "ABC"
    assert evaluate("'  x  '.strip()", _ns()) == "x"
    assert evaluate("'a,b,c'.split(',')", _ns()) == ["a", "b", "c"]
    assert evaluate("'hello'.startswith('he')", _ns()) is True


def test_json_parse_and_stringify():
    assert evaluate('json_parse(\'{"a": 1}\')', _ns()) == {"a": 1}
    assert evaluate("json_stringify({'a': 1})", _ns()) == '{"a": 1}'


def test_dict_get_method():
    ns = _ns(params={"k": 5})
    assert evaluate("params.get('k')", ns) == 5
    assert evaluate("params.get('missing', 9)", ns) == 9


def test_node_result_output_access():
    n1 = NodeResult.single({"price": 10})
    assert evaluate("nodes.n1.output.price * 2", _ns(nodes={"n1": n1})) == 20


def test_node_result_item_access():
    n1 = NodeResult.from_items([Item(json={"sku": "A"}), Item(json={"sku": "B"})])
    assert evaluate("nodes.n1.item.sku", _ns(nodes={"n1": n1})) == "A"


def test_whole_expression_returns_list_type():
    result = evaluate("[1, 2, 3]", {})
    assert result == [1, 2, 3]
    assert isinstance(result, list)


def test_item_field_arithmetic():
    ns = _ns(item={"qty": 3, "price": 10})
    assert evaluate("item.qty * item.price", ns) == 30
