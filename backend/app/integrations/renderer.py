from __future__ import annotations

import re
from typing import Any

_FIELDS_RE = re.compile(r"\{\{\s*\$fields\.([A-Za-z0-9_]+)\s*\}\}")
_CRED_RE = re.compile(r"\{\{\s*\$cred\.([A-Za-z0-9_]+)\s*\}\}")


def _render_string(
    text: str,
    *,
    fields: dict[str, Any],
    cred: dict[str, str],
    secret_keys: set[str],
) -> str:
    def fields_repl(m: re.Match[str]) -> str:
        name = m.group(1)
        if name not in fields:
            raise ValueError(f"unknown field {name!r}")
        val = fields[name]
        return "" if val is None else str(val)

    def cred_repl(m: re.Match[str]) -> str:
        name = m.group(1)
        if name not in cred:
            raise ValueError(f"unknown credential field {name!r}")
        secret_keys.add(f"cred.{name}")
        return cred[name]

    out = _FIELDS_RE.sub(fields_repl, text)
    return _CRED_RE.sub(cred_repl, out)


def _walk(
    value: Any,
    *,
    fields: dict[str, Any],
    cred: dict[str, str],
    secret_keys: set[str],
) -> Any:
    if isinstance(value, str):
        if _FIELDS_RE.fullmatch(value.strip()) or _CRED_RE.fullmatch(value.strip()):
            inner = value.strip()[2:-2].strip()
            if inner.startswith("$fields."):
                name = inner.split(".", 1)[1]
                if name not in fields:
                    raise ValueError(f"unknown field {name!r}")
                return fields[name]
            if inner.startswith("$cred."):
                name = inner.split(".", 1)[1]
                if name not in cred:
                    raise ValueError(f"unknown credential field {name!r}")
                secret_keys.add(f"cred.{name}")
                return cred[name]
        return _render_string(value, fields=fields, cred=cred, secret_keys=secret_keys)
    if isinstance(value, list):
        return [
            _walk(v, fields=fields, cred=cred, secret_keys=secret_keys) for v in value
        ]
    if isinstance(value, dict):
        return {
            k: _walk(v, fields=fields, cred=cred, secret_keys=secret_keys)
            for k, v in value.items()
        }
    return value


def render_template(
    value: Any,
    *,
    fields: dict[str, Any],
    cred: dict[str, str],
    secret_keys: set[str] | None = None,
) -> Any:
    keys = secret_keys if secret_keys is not None else set()
    return _walk(value, fields=fields, cred=cred, secret_keys=keys)


__all__ = ["render_template"]
