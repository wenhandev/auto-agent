"""Vision extraction schema validation tests."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.agents.vision import VisionAgent, _validate_json_schema


TITLE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"title": {"type": "string"}},
    "required": ["title"],
}


def test_validate_json_schema_accepts_valid_object() -> None:
    ok, err = _validate_json_schema({"title": "Hello"}, TITLE_SCHEMA)
    assert ok
    assert err == ""


def test_validate_json_schema_rejects_missing_required() -> None:
    ok, err = _validate_json_schema({}, TITLE_SCHEMA)
    assert not ok
    assert "title" in err


@pytest.mark.asyncio
async def test_finalize_extract_without_schema() -> None:
    agent = VisionAgent()
    result = await agent._finalize_extract(
        done_result={"success": True, "summary": '{"free": true}'},
        schema=None,
        goal="anything",
        last_observation=None,
        steps=2,
    )
    assert result["completed"]
    assert result["data"] == {"free": True}


@pytest.mark.asyncio
async def test_finalize_extract_with_schema_and_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = VisionAgent()

    async def fake_repair(
        raw: str, schema: dict[str, Any], goal: str, error: str = "invalid JSON"
    ) -> dict[str, Any]:
        return {"title": "Fixed"}

    monkeypatch.setattr(agent, "_repair_extract", fake_repair)

    result = await agent._finalize_extract(
        done_result={"success": True, "summary": "not-json"},
        schema=TITLE_SCHEMA,
        goal="get title",
        last_observation=None,
        steps=2,
    )
    assert result["completed"]
    assert result["data"]["title"] == "Fixed"


@pytest.mark.asyncio
async def test_finalize_extract_schema_failure_after_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = VisionAgent()

    async def fake_repair(
        raw: str, schema: dict[str, Any], goal: str, error: str = "invalid JSON"
    ) -> dict[str, Any]:
        return {"wrong": 1}

    monkeypatch.setattr(agent, "_repair_extract", fake_repair)

    result = await agent._finalize_extract(
        done_result={"success": True, "summary": "bad"},
        schema=TITLE_SCHEMA,
        goal="get title",
        last_observation=None,
        steps=2,
    )
    assert not result["completed"]
    assert result["reason"] == "schema_validation_failed"
