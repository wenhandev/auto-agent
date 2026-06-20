from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.nodes.result import BinaryRef, Item, NodeResult
from app.services.variable_interpolation import (
    VariableResolutionError,
    resolve_params,
)


def _ctx(**kw: NodeResult) -> dict[str, NodeResult]:
    return dict(kw)


def test_output_path_unchanged():
    ctx = _ctx(n2=NodeResult.single({"product": {"id": "P-42", "name": "x"}}))
    out = resolve_params({"data": "{{nodes.n2.output.product.id}}"}, context=ctx)
    assert out == {"data": "P-42"}


def test_whole_token_preserves_int():
    ctx = _ctx(count=NodeResult.single({"n": 42}))
    out = resolve_params({"max": "{{nodes.count.output.n}}"}, context=ctx)
    assert out == {"max": 42}
    assert isinstance(out["max"], int)


def test_whole_token_preserves_dict():
    ctx = _ctx(fetch=NodeResult.single({"body": {"a": 1, "b": [2, 3]}}))
    out = resolve_params({"payload": "{{nodes.fetch.output.body}}"}, context=ctx)
    assert out == {"payload": {"a": 1, "b": [2, 3]}}


def test_interpolated_produces_string():
    ctx = _ctx(count=NodeResult.single({"n": 42}))
    out = resolve_params({"label": "count={{nodes.count.output.n}}"}, context=ctx)
    assert out == {"label": "count=42"}


def test_list_index_path():
    ctx = _ctx(fetch=NodeResult.single({"items": [{"sku": "A"}, {"sku": "B"}]}))
    out = resolve_params({"first": "{{nodes.fetch.output.items.0.sku}}"}, context=ctx)
    assert out == {"first": "A"}


def test_item_json_sugar():
    n1 = NodeResult.from_items([Item(json={"sku": "A"}), Item(json={"sku": "B"})])
    out = resolve_params({"v": "{{nodes.n1.item.json.sku}}"}, context=_ctx(n1=n1))
    assert out == {"v": "A"}


def test_whitespace_tolerance():
    ctx = _ctx(n2=NodeResult.single({"id": "P"}))
    out = resolve_params({"d": "{{  nodes.n2.output.id  }}"}, context=ctx)
    assert out == {"d": "P"}


def test_unknown_node_id():
    ctx = _ctx(n1=NodeResult.single({}), n2=NodeResult.single({}))
    with pytest.raises(VariableResolutionError) as ei:
        resolve_params({"d": "{{nodes.n_missing.output.x}}"}, context=ctx)
    assert "has not run yet" in str(ei.value)
    assert "n1" in str(ei.value) and "n2" in str(ei.value)


def test_missing_path_with_suggestion():
    ctx = _ctx(n2=NodeResult.single({"product_id": 1, "product_name": "x"}))
    with pytest.raises(VariableResolutionError) as ei:
        resolve_params({"d": "{{nodes.n2.output.product_idd}}"}, context=ctx)
    msg = str(ei.value)
    assert "missing on node 'n2'" in msg
    assert "did you mean" in msg
    assert "output.product_id" in msg


def test_missing_path_no_close_match():
    ctx = _ctx(n2=NodeResult.single({"a": 1, "b": 2}))
    with pytest.raises(VariableResolutionError) as ei:
        resolve_params({"d": "{{nodes.n2.output.completely_unrelated}}"}, context=ctx)
    msg = str(ei.value)
    assert "did you mean" not in msg
    assert "output.a" in msg and "output.b" in msg


def test_unknown_prefix():
    with pytest.raises(VariableResolutionError) as ei:
        resolve_params({"d": "{{node.n1.output.x}}"}, context={})
    assert "supported prefixes: params, nodes, cred" in str(ei.value)


def test_run_context_when_namespace_provided():
    ns = {"context": {"name": "alpha"}, "kind": "poll", "id": "t1"}
    out = resolve_params({"v": "{{run.context.name}}"}, trigger_namespace=ns)
    assert out == {"v": "alpha"}


def test_trigger_kind_when_namespace_provided():
    ns = {"context": {}, "kind": "app", "id": "t2", "headers": {"x-test": "1"}}
    out = resolve_params({"k": "{{trigger.kind}}", "h": "{{trigger.headers.x-test}}"}, trigger_namespace=ns)
    assert out == {"k": "app", "h": "1"}


def test_reserved_run_prefix_without_namespace():
    with pytest.raises(VariableResolutionError) as ei:
        resolve_params({"d": "{{run.input.x}}"}, context={})
    assert "reserved for a future change" in str(ei.value)
    assert "supported prefixes" not in str(ei.value)


def test_reserved_trigger_prefix_without_namespace():
    with pytest.raises(VariableResolutionError) as ei:
        resolve_params({"d": "{{trigger.headers.x}}"}, context={})
    assert "trigger" in str(ei.value)
    assert "reserved for a future change" in str(ei.value)


def test_binary_token_rejected():
    ref = BinaryRef(kind="inline", mime="application/pdf", size=4, data_b64="AAAA")
    n1 = NodeResult.from_items([Item(json={}, binary={"data": ref})])
    with pytest.raises(VariableResolutionError) as ei:
        resolve_params({"d": "{{nodes.n1.item.binary.data}}"}, context=_ctx(n1=n1))
    assert "binary values cannot be interpolated" in str(ei.value)


def test_non_token_passthrough():
    out = resolve_params({"d": "plain text", "n": 5, "b": True}, context={})
    assert out == {"d": "plain text", "n": 5, "b": True}


def test_params_token_whole_value():
    out = resolve_params(
        {"term": "{{params.search_term}}"},
        params_namespace={"search_term": "shoes"},
    )
    assert out == {"term": "shoes"}


def test_params_token_missing():
    with pytest.raises(VariableResolutionError) as ei:
        resolve_params({"d": "{{params.missing}}"}, params_namespace={})
    assert "parameter 'missing' is not set" in str(ei.value)


def test_params_json_path():
    out = resolve_params(
        {"id": "{{params.config.id}}"},
        params_namespace={"config": {"id": 99}},
    )
    assert out == {"id": 99}
