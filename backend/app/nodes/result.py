"""The items data model.

Every node's canonical result is a :class:`NodeResult` carrying both a
backward-compatible ``output`` dict and an ``items`` array of
``{json, binary}`` records (n8n-style). Existing actions keep returning a
plain ``dict``; the executor wraps it via :meth:`NodeResult.single` so
``output`` is identical to before this change.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Literal, Optional


@dataclass
class BinaryRef:
    """A reference to a binary payload attached to an item under a name.

    Small payloads are stored inline (base64); larger payloads reference an
    artifact / sandboxed temp file. Binary is never interpolated into text.
    """

    kind: Literal["inline", "artifact"]
    mime: str
    size: int
    filename: Optional[str] = None
    data_b64: Optional[str] = None
    artifact_id: Optional[str] = None

    def summary(self) -> dict[str, Any]:
        """A bytes-free summary for events / `{{nodes.<id>.items}}` tokens."""
        return {"mime": self.mime, "size": self.size, "filename": self.filename}

    def read_bytes(self) -> bytes:
        if self.kind == "inline":
            return base64.b64decode(self.data_b64 or "")
        if self.artifact_id:
            with open(self.artifact_id, "rb") as fh:
                return fh.read()
        return b""


@dataclass
class Item:
    json: dict[str, Any]
    binary: dict[str, BinaryRef] = field(default_factory=dict)

    def binary_summary(self) -> dict[str, Any]:
        return {name: ref.summary() for name, ref in self.binary.items()}

    def to_summary(self) -> dict[str, Any]:
        out: dict[str, Any] = {"json": self.json}
        if self.binary:
            out["binary"] = self.binary_summary()
        return out


@dataclass
class NodeResult:
    """Canonical node result.

    ``output`` is the backward-compatible primary dict; for a single-item
    node it equals ``items[0].json``. For a multi-item node it equals the
    first item's json (or ``{}`` when the array is empty).
    """

    output: dict[str, Any]
    items: list[Item]

    @classmethod
    def single(
        cls,
        output: Any,
        binary: Optional[dict[str, BinaryRef]] = None,
    ) -> "NodeResult":
        """Wrap a legacy action return (a dict or ``None``) as one item."""
        out = output if isinstance(output, dict) else ({} if output is None else {"value": output})
        return cls(output=out, items=[Item(json=out, binary=binary or {})])

    @classmethod
    def from_items(cls, items: list[Item]) -> "NodeResult":
        output = items[0].json if items else {}
        return cls(output=output, items=list(items))

    def items_summary(self) -> list[dict[str, Any]]:
        return [it.to_summary() for it in self.items]


__all__ = ["BinaryRef", "Item", "NodeResult"]
