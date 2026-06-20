"""Hybrid browser primitive service contract tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas_tasks import TaskResult
from app.services.perception import ElementSignature, IndexedElement, Observation


def _observation() -> Observation:
    return Observation(
        url="https://example.com/login",
        title="Login",
        screenshot_bytes=b"png",
        screenshot_ref="/tmp/fake.png",
        ax_snapshot={},
        elements=[
            IndexedElement(
                index=0,
                role="button",
                name="Sign in",
                signature=ElementSignature(role="button", name="Sign in"),
                ref="ref_sign_in",
            )
        ],
        page_text_summary="Sign in to continue",
    )


@pytest.mark.asyncio
async def test_observe_returns_candidates_without_page_side_effects() -> None:
    from app.services.browser_primitives import BrowserPrimitiveService, ObserveRequest

    page = MagicMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.goto = AsyncMock()
    events: list[dict[str, Any]] = []

    service = BrowserPrimitiveService(
        page_provider=AsyncMock(return_value=page),
        perceive_fn=AsyncMock(return_value=_observation()),
    )

    result = await service.observe(
        ObserveRequest(instruction="find the sign in button"),
        emit=events.append,
    )

    assert result.url == "https://example.com/login"
    assert result.candidates[0].index == 0
    assert result.candidates[0].role == "button"
    assert result.candidates[0].label == "Sign in"
    assert result.candidates[0].source == "perception"
    page.click.assert_not_awaited()
    page.fill.assert_not_awaited()
    page.goto.assert_not_awaited()
    assert events == [
        {
            "event": "primitive_observe",
            "instruction": "find the sign in button",
            "url": "https://example.com/login",
            "candidate_count": 1,
            "sources": ["perception"],
        }
    ]


@pytest.mark.asyncio
async def test_act_executes_exactly_one_resolved_action() -> None:
    from app.services.browser_primitives import (
        ActRequest,
        BrowserPrimitiveService,
        PrimitiveAction,
    )

    events: list[dict[str, Any]] = []

    async def fake_executor(action: PrimitiveAction, observation: Observation) -> dict[str, Any]:
        return {"clicked_index": action.args["index"], "url": observation.url}

    service = BrowserPrimitiveService(
        page_provider=AsyncMock(return_value=MagicMock()),
        perceive_fn=AsyncMock(return_value=_observation()),
        action_resolver=AsyncMock(
            return_value=PrimitiveAction(name="click_element", args={"index": 0})
        ),
        action_executor=fake_executor,
    )

    result = await service.act(
        ActRequest(instruction="click sign in"),
        emit=events.append,
    )

    assert result.action == "click_element"
    assert result.result == {"clicked_index": 0, "url": "https://example.com/login"}
    assert result.source == "resolver"
    assert events == [
        {
            "event": "primitive_act",
            "instruction": "click sign in",
            "url": "https://example.com/login",
            "action": "click_element",
            "source": "resolver",
            "result": {"clicked_index": 0, "url": "https://example.com/login"},
        }
    ]


@pytest.mark.asyncio
async def test_act_uses_cached_action_before_resolver() -> None:
    from app.services.browser_primitives import (
        ActRequest,
        BrowserPrimitiveService,
        PrimitiveAction,
    )

    resolver = AsyncMock(
        return_value=PrimitiveAction(name="click_element", args={"index": 999})
    )

    async def fake_executor(action: PrimitiveAction, observation: Observation) -> dict[str, Any]:
        return {"clicked_index": action.args["index"], "url": observation.url}

    service = BrowserPrimitiveService(
        page_provider=AsyncMock(return_value=MagicMock()),
        perceive_fn=AsyncMock(return_value=_observation()),
        action_resolver=resolver,
        action_executor=fake_executor,
        cache_lookup=AsyncMock(
            return_value=PrimitiveAction(name="click_element", args={"index": 0})
        ),
    )

    result = await service.act(ActRequest(instruction="click sign in"))

    assert result.source == "cache"
    assert result.result == {"clicked_index": 0, "url": "https://example.com/login"}
    resolver.assert_not_awaited()


@pytest.mark.asyncio
async def test_act_writes_successful_resolved_action_to_cache() -> None:
    from app.services.browser_primitives import (
        ActRequest,
        BrowserPrimitiveService,
        PrimitiveAction,
    )

    cache_write = AsyncMock()

    async def fake_executor(action: PrimitiveAction, observation: Observation) -> dict[str, Any]:
        return {"clicked_index": action.args["index"], "url": observation.url}

    service = BrowserPrimitiveService(
        page_provider=AsyncMock(return_value=MagicMock()),
        perceive_fn=AsyncMock(return_value=_observation()),
        action_resolver=AsyncMock(
            return_value=PrimitiveAction(name="click_element", args={"index": 0})
        ),
        action_executor=fake_executor,
        cache_write=cache_write,
    )

    await service.act(ActRequest(instruction="click sign in"))

    cache_write.assert_awaited_once()
    _, action, observation, result = cache_write.await_args.args
    assert action.name == "click_element"
    assert observation.url == "https://example.com/login"
    assert result == {"clicked_index": 0, "url": "https://example.com/login"}


@pytest.mark.asyncio
async def test_act_cache_write_derives_plan_from_ref_action() -> None:
    from app.services.browser_primitives import (
        ActRequest,
        BrowserPrimitiveService,
        PrimitiveAction,
    )

    cache_write = AsyncMock()

    async def fake_executor(action: PrimitiveAction, observation: Observation) -> dict[str, Any]:
        return {"clicked_ref": action.args["ref"], "clicked_index": 0, "url": observation.url}

    service = BrowserPrimitiveService(
        page_provider=AsyncMock(return_value=MagicMock()),
        perceive_fn=AsyncMock(return_value=_observation()),
        action_resolver=AsyncMock(
            return_value=PrimitiveAction(name="click_element", args={"ref": "ref_sign_in"})
        ),
        action_executor=fake_executor,
        cache_write=cache_write,
    )

    await service.act(ActRequest(instruction="click sign in"))

    _, action, _observation_arg, _result = cache_write.await_args.args
    assert action.args == {"index": 0}


@pytest.mark.asyncio
async def test_extract_validates_schema() -> None:
    from app.services.browser_primitives import BrowserPrimitiveService, ExtractRequest

    service = BrowserPrimitiveService(
        page_provider=AsyncMock(return_value=MagicMock()),
        extract_fn=AsyncMock(return_value={"price": 199}),
    )

    result = await service.extract(
        ExtractRequest(
            instruction="extract price",
            schema={
                "type": "object",
                "properties": {"price": {"type": "number"}},
                "required": ["price"],
            },
        )
    )

    assert result.valid is True
    assert result.data == {"price": 199}
    assert result.error is None


@pytest.mark.asyncio
async def test_extract_returns_validation_error() -> None:
    from app.services.browser_primitives import BrowserPrimitiveService, ExtractRequest

    service = BrowserPrimitiveService(
        page_provider=AsyncMock(return_value=MagicMock()),
        extract_fn=AsyncMock(return_value={"price": "expensive"}),
    )

    result = await service.extract(
        ExtractRequest(
            instruction="extract price",
            schema={
                "type": "object",
                "properties": {"price": {"type": "number"}},
                "required": ["price"],
            },
        )
    )

    assert result.valid is False
    assert result.data == {"price": "expensive"}
    assert "price" in (result.error or "")


@pytest.mark.asyncio
async def test_agent_task_delegates_to_task_runner_and_emits_events() -> None:
    from app.services.browser_primitives import AgentTaskRequest, BrowserPrimitiveService

    captured_events: list[dict[str, Any]] = []

    async def fake_task_runner(spec, emit):
        await emit({"event": "task_plan_updated", "plan": []})
        return TaskResult(success=True, summary="done", steps_taken=1)

    service = BrowserPrimitiveService(task_runner=fake_task_runner)

    result = await service.agent_task(
        AgentTaskRequest(objective="log in", start_url="https://example.com"),
        emit=captured_events.append,
    )

    assert result.result.success is True
    assert result.result.summary == "done"
    assert captured_events == [{"event": "task_plan_updated", "plan": []}]


@pytest.mark.asyncio
async def test_agent_task_appends_compact_memory_for_browser_session() -> None:
    from app.services.browser_primitives import (
        AgentTaskRequest,
        BrowserPrimitiveService,
        PrimitiveContext,
    )

    appended: list[dict[str, Any]] = []

    async def fake_task_runner(spec, emit):
        return TaskResult(
            success=True,
            summary="downloaded invoice",
            items=[{"invoice": "A-1"}],
            steps_taken=1,
        )

    async def fake_memory_appender(session_id: str, request, result: TaskResult) -> None:
        appended.append(
            {
                "session_id": session_id,
                "objective": request.objective,
                "success": result.success,
                "summary": result.summary,
                "items": result.items,
            }
        )

    service = BrowserPrimitiveService(
        task_runner=fake_task_runner,
        memory_loader=AsyncMock(return_value=[]),
        memory_appender=fake_memory_appender,
    )

    await service.agent_task(
        AgentTaskRequest(
            objective="download invoice",
            context=PrimitiveContext(browser_session_id="session-1"),
        )
    )

    assert appended == [
        {
            "session_id": "session-1",
            "objective": "download invoice",
            "success": True,
            "summary": "downloaded invoice",
            "items": [{"invoice": "A-1"}],
        }
    ]


@pytest.mark.asyncio
async def test_agent_task_injects_session_memory_into_task_spec() -> None:
    from app.services.browser_primitives import (
        AgentTaskRequest,
        BrowserPrimitiveService,
        PrimitiveContext,
    )

    captured: dict[str, Any] = {}

    async def fake_task_runner(spec, emit):
        captured["session_memory"] = spec.session_memory
        return TaskResult(success=True, summary="done")

    async def fake_memory_loader(session_id: str) -> list[dict[str, Any]]:
        return [{"objective": "previous", "summary": "already logged in"}]

    service = BrowserPrimitiveService(
        task_runner=fake_task_runner,
        memory_loader=fake_memory_loader,
        memory_appender=AsyncMock(),
    )

    await service.agent_task(
        AgentTaskRequest(
            objective="continue task",
            context=PrimitiveContext(browser_session_id="session-1"),
        )
    )

    assert captured["session_memory"] == [
        {"objective": "previous", "summary": "already logged in"}
    ]


@pytest.mark.asyncio
async def test_primitive_persists_event_from_run_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import artifact_context
    from app.services.browser_primitives import BrowserPrimitiveService, ObserveRequest

    persisted: list[tuple[str, int, dict[str, Any]]] = []

    monkeypatch.setattr(
        "app.services.browser_primitives.run_svc.fetch_prior_events",
        lambda run_id: [{"event": "existing"}],
    )
    monkeypatch.setattr(
        "app.services.browser_primitives.run_svc.persist_and_fanout",
        lambda run_id, seq, payload: persisted.append((run_id, seq, payload)),
    )

    service = BrowserPrimitiveService(
        page_provider=AsyncMock(return_value=MagicMock()),
        perceive_fn=AsyncMock(return_value=_observation()),
    )

    artifact_context.set_run_context("run-123")
    try:
        await service.observe(ObserveRequest(instruction="find sign in"))
    finally:
        artifact_context.clear_run_context()

    assert persisted == [
        (
            "run-123",
            1,
            {
                "event": "primitive_observe",
                "instruction": "find sign in",
                "url": "https://example.com/login",
                "candidate_count": 1,
                "sources": ["perception"],
                "run_id": "run-123",
                "seq": 1,
            },
        )
    ]
