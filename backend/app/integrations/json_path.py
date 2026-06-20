from __future__ import annotations

import re
from typing import Any

_FIELDS_RE = re.compile(r"\{\{\s*\$fields\.([A-Za-z0-9_]+)\s*\}\}")
_CRED_RE = re.compile(r"\{\{\s*\$cred\.([A-Za-z0-9_]+)\s*\}\}")


def resolve_path(obj: Any, path: str) -> Any:
    """JSONPath-lite: dot-separated segments with numeric array indices."""
    if not path:
        return obj
    cur = obj
    for seg in path.split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(seg)]
            except (ValueError, IndexError) as exc:
                raise ValueError(f"path segment {seg!r} invalid for list") from exc
        elif isinstance(cur, dict):
            if seg not in cur:
                raise ValueError(f"path segment {seg!r} missing")
            cur = cur[seg]
        else:
            raise ValueError(f"cannot traverse into {type(cur).__name__} at {seg!r}")
    return cur


def extract_field_refs(value: Any) -> set[str]:
    refs: set[str] = set()

    def walk(v: Any) -> None:
        if isinstance(v, str):
            refs.update(_FIELDS_RE.findall(v))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(value)
    return refs


def extract_cred_refs(value: Any) -> set[str]:
    refs: set[str] = set()

    def walk(v: Any) -> None:
        if isinstance(v, str):
            refs.update(_CRED_RE.findall(v))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(value)
    return refs


__all__ = ["extract_cred_refs", "extract_field_refs", "resolve_path"]
