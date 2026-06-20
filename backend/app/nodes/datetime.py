from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.nodes._helpers import build_namespace
from app.nodes.result import Item
from app.services.expressions import ExpressionError, _date_add, _format_date, _now, _parse_date


def _apply_duration(value: datetime, duration: dict[str, Any], *, subtract: bool) -> datetime:
    amount = float(duration.get("value", 0))
    unit = str(duration.get("unit", "days"))
    sign = -1 if subtract else 1
    kwargs: dict[str, float] = {}
    if unit in ("day", "days"):
        kwargs["days"] = sign * amount
    elif unit in ("hour", "hours"):
        kwargs["hours"] = sign * amount
    elif unit in ("minute", "minutes"):
        kwargs["minutes"] = sign * amount
    elif unit in ("second", "seconds"):
        kwargs["seconds"] = sign * amount
    elif unit in ("week", "weeks"):
        kwargs["weeks"] = sign * amount
    else:
        raise ExpressionError(f"datetime: unknown unit {unit!r}")
    return _date_add(value, **kwargs)


async def run(
    params: dict[str, Any],
    *,
    input_items: list[Item],
    context: dict[str, Any],
) -> list[Item]:
    action = str(params.get("action", "now"))
    field = params.get("field")
    output_field = str(params.get("output_field") or field or "ts")
    fmt = params.get("format")
    duration = params.get("duration") or {}

    if action == "now" and not input_items:
        ts = _now()
        return [Item(json={output_field: ts.isoformat()})]

    out: list[Item] = []
    for item in input_items:
        _ = build_namespace(item, input_items, context)
        data = dict(item.json)

        if action == "now":
            value: Any = _now()
        elif action == "parse":
            raw = data.get(str(field)) if field else None
            value = _parse_date(raw, fmt)
        elif action == "format":
            raw = data.get(str(field)) if field else None
            if fmt is None:
                raise ExpressionError("datetime format requires a format string")
            value = _format_date(raw, str(fmt))
        elif action in ("add", "subtract"):
            raw = data.get(str(field)) if field else None
            dt = _parse_date(raw) if raw is not None else _now()
            value = _apply_duration(dt, duration, subtract=action == "subtract")
            if isinstance(value, datetime) and value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            if action in ("add", "subtract") and fmt:
                value = _format_date(value, str(fmt))
            elif action in ("add", "subtract") and isinstance(value, datetime):
                value = value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            raise ExpressionError(f"datetime: unknown action {action!r}")

        if isinstance(value, datetime):
            stored: Any = value.isoformat()
        else:
            stored = value

        if field and action != "now":
            data[str(field)] = stored
        else:
            data[output_field] = stored
        out.append(Item(json=data, binary=dict(item.binary)))
    return out
