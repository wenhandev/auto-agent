from __future__ import annotations

from typing import Any

from app.integrations.bootstrap import bootstrap_integrations
from app.integrations.loader import load_descriptors
from app.integrations.schema import IntegrationCatalogueEntry, IntegrationDescriptor, TriggerDescriptor

_registry: dict[str, IntegrationDescriptor] | None = None


def load_integrations() -> dict[str, IntegrationDescriptor]:
    global _registry
    bootstrap_integrations()
    _registry = load_descriptors()
    return _registry


def get_registry() -> dict[str, IntegrationDescriptor]:
    if _registry is None:
        return load_integrations()
    return _registry


def get_descriptor(app: str) -> IntegrationDescriptor:
    reg = get_registry()
    if app not in reg:
        raise KeyError(f"unknown integration app {app!r}")
    return reg[app]


def catalogue() -> list[IntegrationCatalogueEntry]:
    reg = get_registry()
    out: list[IntegrationCatalogueEntry] = []
    for desc in reg.values():
        resources = [
            {
                "name": r.name,
                "label": r.label,
                "operations": [{"name": o.name, "label": o.label} for o in r.operations],
            }
            for r in desc.resources
        ]
        triggers = [
            {
                "name": t.name,
                "label": t.label,
                "kind": t.kind,
                "resource": t.resource,
                "list_operation": t.list_operation,
                "dedup_path": t.dedup_path,
            }
            for t in desc.triggers
        ]
        out.append(
            IntegrationCatalogueEntry(
                app=desc.app,
                version=desc.version,
                credentials=list(desc.credentials),
                resources=resources,
                triggers=triggers,
            )
        )
    return sorted(out, key=lambda e: e.app)


def resolve_operation(app: str, resource: str, operation: str):
    desc = get_descriptor(app)
    for res in desc.resources:
        if res.name != resource:
            continue
        for op in res.operations:
            if op.name == operation:
                return desc, res, op
    raise KeyError(
        f"operation {operation!r} not found in app {app!r} resource {resource!r}"
    )


def resolve_trigger_descriptor(app: str, trigger_name: str) -> tuple[IntegrationDescriptor, TriggerDescriptor]:
    desc = get_descriptor(app)
    for trig in desc.triggers:
        if trig.name == trigger_name:
            return desc, trig
    raise KeyError(
        f"trigger {trigger_name!r} not found in app {app!r}"
    )


__all__ = [
    "catalogue",
    "get_descriptor",
    "get_registry",
    "load_integrations",
    "resolve_operation",
    "resolve_trigger_descriptor",
]
