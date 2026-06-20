from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path
from typing import Any

from app.integrations.credential_types import get_credential_type
from app.integrations.json_path import extract_cred_refs, extract_field_refs
from app.integrations.schema import IntegrationDescriptor, Operation, Resource, TriggerDescriptor

logger = logging.getLogger(__name__)

_INTEGRATIONS_ROOT = Path(__file__).resolve().parent


class DescriptorLoadError(ValueError):
    pass


def _load_descriptor_file(path: Path) -> IntegrationDescriptor:
    if path.suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return IntegrationDescriptor.model_validate(data)

    if path.suffix == ".py":
        spec = importlib.util.spec_from_file_location(f"integration_{path.stem}", path)
        if spec is None or spec.loader is None:
            raise DescriptorLoadError(f"cannot import descriptor module {path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "DESCRIPTOR"):
            raw = mod.DESCRIPTOR
        elif hasattr(mod, "descriptor"):
            raw = mod.descriptor
        else:
            raise DescriptorLoadError(
                f"descriptor module {path} must define DESCRIPTOR or descriptor"
            )
        if isinstance(raw, IntegrationDescriptor):
            return raw
        return IntegrationDescriptor.model_validate(raw)

    raise DescriptorLoadError(f"unsupported descriptor format: {path.suffix}")


def _validate_operation_refs(
    app: str,
    resource: Resource,
    op: Operation,
    cred_field_names: set[str],
) -> None:
    declared = {f.name for f in op.fields}
    templates: list[Any] = [
        op.request.url,
        op.request.query,
        op.request.headers,
        op.request.body,
    ]
    for tmpl in templates:
        for ref in extract_field_refs(tmpl):
            if ref not in declared:
                raise DescriptorLoadError(
                    f"app {app!r} resource {resource.name!r} operation {op.name!r}: "
                    f"request references undeclared field {ref!r}"
                )
        for ref in extract_cred_refs(tmpl):
            if ref not in cred_field_names:
                raise DescriptorLoadError(
                    f"app {app!r} resource {resource.name!r} operation {op.name!r}: "
                    f"request references unknown credential field {ref!r}"
                )


def _operation_names(desc: IntegrationDescriptor) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for resource in desc.resources:
        out[resource.name] = {op.name for op in resource.operations}
    return out


def _validate_trigger_descriptor(
    desc: IntegrationDescriptor,
    trig: TriggerDescriptor,
    ops_by_resource: dict[str, set[str]],
) -> None:
    resource = trig.resource
    if trig.kind == "poll":
        if not trig.list_operation:
            raise DescriptorLoadError(
                f"app {desc.app!r} trigger {trig.name!r}: poll trigger requires list_operation"
            )
        if not trig.dedup_path:
            raise DescriptorLoadError(
                f"app {desc.app!r} trigger {trig.name!r}: poll trigger requires dedup_path"
            )
        res = resource or desc.resources[0].name if desc.resources else None
        if res is None or res not in ops_by_resource:
            raise DescriptorLoadError(
                f"app {desc.app!r} trigger {trig.name!r}: unknown resource {res!r}"
            )
        if trig.list_operation not in ops_by_resource[res]:
            raise DescriptorLoadError(
                f"app {desc.app!r} trigger {trig.name!r}: "
                f"unknown list_operation {trig.list_operation!r}"
            )
    elif trig.kind == "webhook":
        if not trig.subscribe_operation or not trig.unsubscribe_operation:
            raise DescriptorLoadError(
                f"app {desc.app!r} trigger {trig.name!r}: "
                "webhook trigger requires subscribe_operation and unsubscribe_operation"
            )
        res = resource or desc.resources[0].name if desc.resources else None
        if res is None or res not in ops_by_resource:
            raise DescriptorLoadError(
                f"app {desc.app!r} trigger {trig.name!r}: unknown resource {res!r}"
            )
        for op_name in (trig.subscribe_operation, trig.unsubscribe_operation):
            if op_name not in ops_by_resource[res]:
                raise DescriptorLoadError(
                    f"app {desc.app!r} trigger {trig.name!r}: "
                    f"unknown operation {op_name!r}"
                )


def _validate_descriptor(desc: IntegrationDescriptor) -> None:
    for cred_type_name in desc.credentials:
        ct = get_credential_type(cred_type_name)
        if ct is None:
            raise DescriptorLoadError(
                f"app {desc.app!r}: unknown credential type {cred_type_name!r}"
            )

    cred_fields: set[str] = set()
    for cred_type_name in desc.credentials:
        ct = get_credential_type(cred_type_name)
        assert ct is not None
        cred_fields.update(f.name for f in ct.fields)
        cred_fields.update(
            {
                "access_token",
                "refresh_token",
                "expires_at",
            }
        )

    for resource in desc.resources:
        for op in resource.operations:
            _validate_operation_refs(desc.app, resource, op, cred_fields)
            resp = op.response
            if resp.item_path is None and resp.root_path is None:
                raise DescriptorLoadError(
                    f"app {desc.app!r} resource {resource.name!r} "
                    f"operation {op.name!r}: response must set item_path or root_path"
                )

    ops_by_resource = _operation_names(desc)
    seen_trigger_names: set[str] = set()
    for trig in desc.triggers:
        if trig.name in seen_trigger_names:
            raise DescriptorLoadError(
                f"app {desc.app!r}: duplicate trigger name {trig.name!r}"
            )
        seen_trigger_names.add(trig.name)
        _validate_trigger_descriptor(desc, trig, ops_by_resource)


def discover_descriptor_paths(root: Path | None = None) -> list[Path]:
    base = root or _INTEGRATIONS_ROOT
    paths: list[Path] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir() or child.name == "__pycache__":
            continue
        if child.name.startswith("_") and child.name != "_fixture":
            continue
        for name in ("descriptor.json", "descriptor.py"):
            candidate = child / name
            if candidate.exists():
                paths.append(candidate)
                break
    return paths


def load_descriptors(root: Path | None = None) -> dict[str, IntegrationDescriptor]:
    registry: dict[str, IntegrationDescriptor] = {}
    for path in discover_descriptor_paths(root):
        try:
            desc = _load_descriptor_file(path)
        except Exception as exc:
            raise DescriptorLoadError(f"failed to load {path}: {exc}") from exc
        try:
            _validate_descriptor(desc)
        except DescriptorLoadError:
            raise
        except Exception as exc:
            raise DescriptorLoadError(
                f"app {desc.app!r}: validation failed: {exc}"
            ) from exc
        if desc.app in registry:
            raise DescriptorLoadError(f"duplicate app id {desc.app!r}")
        registry[desc.app] = desc
        logger.info("loaded integration descriptor app=%s version=%s", desc.app, desc.version)
    return registry


__all__ = ["DescriptorLoadError", "discover_descriptor_paths", "load_descriptors"]
