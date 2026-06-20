from __future__ import annotations

from app.integrations.registry import get_registry


def integration_catalogue_prompt(*, skip_fixture: bool = True) -> str:
    """Compact integration node catalogue for planner/editor prompts."""
    reg = get_registry()
    lines: list[str] = [
        '  - "integration" params: { "app": str, "resource": str, "operation": str,',
        '      "credential": str (linked credential name, e.g. "my-slack"),',
        '      "fields": { <operation field names>: <values or node interpolation tokens> } }',
        "    Available apps and operations:",
    ]
    for app in sorted(reg.keys()):
        if skip_fixture and app.startswith("_"):
            continue
        desc = reg[app]
        for res in desc.resources:
            for op in res.operations:
                field_names = [f.name for f in op.fields]
                fields_hint = ", ".join(field_names) if field_names else "(no fields)"
                lines.append(
                    f"    - {app}/{res.name}/{op.name}"
                    f" ({op.label or op.name}): fields=[{fields_hint}]"
                )
    lines.append(
        '    Example: post to Slack #general — '
        '{"type":"integration","params":{"app":"slack","resource":"chat",'
        '"operation":"postMessage","credential":"my-slack",'
        '"fields":{"channel":"#general","text":"Hello"}}}'
    )
    return "\n".join(lines)


__all__ = ["integration_catalogue_prompt"]
