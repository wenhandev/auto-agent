from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.integrations.loader import DescriptorLoadError, load_descriptors
from app.integrations.registry import catalogue, load_integrations


@pytest.fixture(autouse=True)
def _fresh_registry():
    load_integrations()
    yield


def test_fixture_descriptor_loads():
    reg = load_descriptors()
    assert "_fixture" in reg
    desc = reg["_fixture"]
    assert desc.version == "1.0.0"
    assert len(desc.resources) == 2
    assert desc.resources[0].operations[0].name == "list"
    assert len(desc.triggers) == 2
    assert desc.triggers[0].kind == "poll"


def test_unknown_credential_type_rejected(tmp_path: Path):
    bad = {
        "app": "bad_app",
        "version": "1",
        "credentials": ["nonexistent_type"],
        "resources": [
            {
                "name": "r",
                "label": "R",
                "operations": [
                    {
                        "name": "op",
                        "label": "Op",
                        "fields": [],
                        "request": {
                            "method": "GET",
                            "url": "https://example.com/x",
                        },
                        "response": {"root_path": "data"},
                    }
                ],
            }
        ],
    }
    app_dir = tmp_path / "bad_app"
    app_dir.mkdir()
    (app_dir / "descriptor.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(DescriptorLoadError, match="unknown credential type"):
        load_descriptors(tmp_path)


def test_undeclared_field_rejected(tmp_path: Path):
    bad = {
        "app": "bad_fields",
        "version": "1",
        "credentials": [],
        "resources": [
            {
                "name": "r",
                "label": "R",
                "operations": [
                    {
                        "name": "op",
                        "label": "Op",
                        "fields": [],
                        "request": {
                            "method": "GET",
                            "url": "https://example.com/{{$fields.missing}}",
                        },
                        "response": {"root_path": "data"},
                    }
                ],
            }
        ],
    }
    app_dir = tmp_path / "bad_fields"
    app_dir.mkdir()
    (app_dir / "descriptor.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(DescriptorLoadError, match="undeclared field"):
        load_descriptors(tmp_path)


def test_catalogue_shape():
    entries = catalogue()
    apps = {e.app for e in entries}
    assert "_fixture" in apps
    fixture = next(e for e in entries if e.app == "_fixture")
    assert fixture.resources[0]["name"] == "records"
    op_names = [o["name"] for o in fixture.resources[0]["operations"]]
    assert "list" in op_names and "get" in op_names
