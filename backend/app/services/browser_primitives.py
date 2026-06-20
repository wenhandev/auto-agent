"""Hybrid browser primitives over the existing browser/perception stack."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.agents.vision import _validate_json_schema
from app.schemas_tasks import TaskResult, TaskSpec
from app.services import artifact_context
from app.services import runs as run_svc
from app.services.computer_use import (
    ComputerUseAction,
    ComputerUseRuntime,
    computer_use_enabled,
    should_attempt_computer_use_fallback,
)
from app.services.perception import Observation, resolve_element, resolve_ref


EmitFn = Callable[[dict[str, Any]], Any]
PageProvider = Callable[[], Awaitable[Any]]
PerceiveFn = Callable[[Any], Awaitable[Observation]]
ActionResolver = Callable[["ActRequest", Observation], Awaitable["PrimitiveAction"]]
ActionExecutor = Callable[["PrimitiveAction", Observation], Awaitable[dict[str, Any]]]
CacheLookup = Callable[["ActRequest", Observation], Awaitable[Optional["PrimitiveAction"]]]
CacheWrite = Callable[
    ["ActRequest", "PrimitiveAction", Observation, dict[str, Any]],
    Awaitable[None],
]
ExtractFn = Callable[[Any, str, Optional[dict[str, Any]]], Awaitable[Any]]
TaskRunner = Callable[[TaskSpec, EmitFn], Awaitable[TaskResult]]
MemoryAppender = Callable[[str, "AgentTaskRequest", TaskResult], Awaitable[None]]
MemoryLoader = Callable[[str], Awaitable[list[dict[str, Any]]]]
ComputerUseFallback = Callable[
    ["ActRequest", Observation, dict[str, Any]],
    Awaitable[Optional[ComputerUseAction]],
]
ComputerUseExecute = Callable[..., Awaitable[dict[str, Any]]]


class PrimitiveContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: Optional[str] = None
    browser_session_id: Optional[str] = None
    allowed_domains: Optional[list[str]] = None
    allowed_tools: Optional[list[str]] = None
    require_confirmation: bool = False


class ObserveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str
    context: PrimitiveContext = Field(default_factory=PrimitiveContext)


class ActRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str
    context: PrimitiveContext = Field(default_factory=PrimitiveContext)


class ExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    instruction: str
    extraction_schema: Optional[dict[str, Any]] = Field(default=None, alias="schema")
    context: PrimitiveContext = Field(default_factory=PrimitiveContext)


class AgentTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str
    start_url: Optional[str] = None
    max_steps: int = 30
    max_seconds: int = 300
    success_criteria: Optional[str] = None
    allowed_domains: Optional[list[str]] = None
    data_schema: Optional[dict[str, Any]] = None
    require_confirmation: bool = False
    allowed_tools: Optional[list[str]] = None
    synthesize_workflow: bool = True
    context: PrimitiveContext = Field(default_factory=PrimitiveContext)


class PrimitiveCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str
    index: int
    role: str
    label: str
    confidence: float = 1.0
    source: str = "perception"


class ObserveResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str
    url: str
    title: str
    candidates: list[PrimitiveCandidate]


class PrimitiveAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class ActResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str
    url: str
    action: str
    result: dict[str, Any]
    source: str


class ExtractResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str
    data: Any = None
    valid: bool
    error: Optional[str] = None


class AgentTaskPrimitiveResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: TaskResult


async def _default_page_provider() -> Any:
    from app.tools.browser import get_page

    return await get_page()


async def _default_perceive(page: Any) -> Observation:
    from app.services.perception import perceive

    return await perceive(page, ref_hint="primitive")


async def _default_action_resolver(
    request: ActRequest,
    observation: Observation,
) -> PrimitiveAction:
    if observation.elements:
        return PrimitiveAction(name="click_element", args={"index": observation.elements[0].index})
    raise RuntimeError(f"could not resolve action for instruction {request.instruction!r}")


async def _default_cache_lookup(
    request: ActRequest,
    observation: Observation,
) -> Optional[PrimitiveAction]:
    return None


async def _default_cache_write(
    request: ActRequest,
    action: PrimitiveAction,
    observation: Observation,
    result: dict[str, Any],
) -> None:
    return None


async def _default_extract(
    page: Any,
    instruction: str,
    schema: Optional[dict[str, Any]],
) -> Any:
    from app.tools import actions

    result = await actions.extract(instruction)
    if isinstance(result, dict) and "data" in result:
        return result["data"]
    return result


async def _default_task_runner(spec: TaskSpec, emit: EmitFn) -> TaskResult:
    from app.agents.autonomous import run_task

    return await run_task(spec, emit)


async def _default_memory_loader(session_id: str) -> list[dict[str, Any]]:
    from sqlmodel import Session

    from app.db.session import engine
    from app.services import browser_sessions as session_svc

    with Session(engine) as session:
        return session_svc.list_memory_entries(session, session_id)


async def _default_computer_use_fallback(
    request: ActRequest,
    observation: Observation,
    structured_result: dict[str, Any],
) -> Optional[ComputerUseAction]:
    return None


async def _default_computer_use_execute(
    *,
    action: ComputerUseAction,
    reason: str,
    allowed_domains: Optional[list[str]],
    require_confirmation: bool,
    emit: Optional[EmitFn],
    page_provider: PageProvider,
) -> dict[str, Any]:
    runtime = ComputerUseRuntime(page_provider=page_provider)
    return await runtime.execute(
        action,
        reason=reason,
        allowed_domains=allowed_domains,
        require_confirmation=require_confirmation,
        destructive=action.destructive,
        emit=emit,
    )


async def _default_memory_appender(
    session_id: str,
    request: AgentTaskRequest,
    result: TaskResult,
) -> None:
    from sqlmodel import Session

    from app.db.session import engine
    from app.services import browser_sessions as session_svc

    with Session(engine) as session:
        session_svc.append_memory_entry(
            session,
            session_id,
            objective=request.objective,
            success=result.success,
            summary=result.summary,
            final_url=None,
            extracted_items=list(result.items),
        )


def _persist_context_event(payload: dict[str, Any]) -> None:
    run_id = artifact_context.get_run_id()
    if not run_id:
        return
    seq = len(run_svc.fetch_prior_events(run_id))
    enriched = {**payload, "run_id": run_id, "seq": seq}
    run_svc.persist_and_fanout(run_id, seq, enriched)


async def _maybe_emit(emit: Optional[EmitFn], payload: dict[str, Any]) -> None:
    if emit is None:
        _persist_context_event(payload)
        return
    result = emit(payload)
    if inspect.isawaitable(result):
        await result


def _cacheable_action(action: PrimitiveAction, observation: Observation) -> PrimitiveAction:
    if "ref" not in action.args:
        return action
    try:
        element = resolve_ref(observation, str(action.args["ref"]))
    except ValueError:
        return action
    args = dict(action.args)
    args.pop("ref", None)
    args.setdefault("index", element.index)
    return PrimitiveAction(name=action.name, args=args)


class BrowserPrimitiveService:
    """Service boundary for observe/act/extract/agent_task primitives."""

    def __init__(
        self,
        *,
        page_provider: PageProvider = _default_page_provider,
        perceive_fn: PerceiveFn = _default_perceive,
        action_resolver: ActionResolver = _default_action_resolver,
        action_executor: Optional[ActionExecutor] = None,
        cache_lookup: CacheLookup = _default_cache_lookup,
        cache_write: CacheWrite = _default_cache_write,
        extract_fn: ExtractFn = _default_extract,
        task_runner: TaskRunner = _default_task_runner,
        memory_loader: MemoryLoader = _default_memory_loader,
        memory_appender: MemoryAppender = _default_memory_appender,
        computer_use_fallback: ComputerUseFallback = _default_computer_use_fallback,
        computer_use_execute: Optional[ComputerUseExecute] = None,
    ) -> None:
        self._page_provider = page_provider
        self._perceive = perceive_fn
        self._action_resolver = action_resolver
        self._action_executor = action_executor or self._execute_action
        self._cache_lookup = cache_lookup
        self._cache_write = cache_write
        self._extract = extract_fn
        self._task_runner = task_runner
        self._memory_loader = memory_loader
        self._memory_appender = memory_appender
        self._computer_use_fallback = computer_use_fallback
        self._computer_use_execute = computer_use_execute

    async def observe(
        self,
        request: ObserveRequest,
        *,
        emit: Optional[EmitFn] = None,
    ) -> ObserveResult:
        page = await self._page_provider()
        observation = await self._perceive(page)
        candidates = [
            PrimitiveCandidate(
                ref=f"e{el.index}",
                index=el.index,
                role=el.role,
                label=el.name,
            )
            for el in observation.elements
        ]
        sources = sorted({candidate.source for candidate in candidates}) or ["perception"]
        await _maybe_emit(
            emit,
            {
                "event": "primitive_observe",
                "instruction": request.instruction,
                "url": observation.url,
                "candidate_count": len(candidates),
                "sources": sources,
            },
        )
        return ObserveResult(
            instruction=request.instruction,
            url=observation.url,
            title=observation.title,
            candidates=candidates,
        )

    async def act(
        self,
        request: ActRequest,
        *,
        emit: Optional[EmitFn] = None,
    ) -> ActResult:
        page = await self._page_provider()
        observation = await self._perceive(page)
        source = "cache"
        action = await self._cache_lookup(request, observation)
        from app.services.agent_loop_metrics import get_metrics

        metrics = get_metrics()
        if action is None:
            source = "resolver"
            if metrics is not None:
                metrics.record_cache(hit=False)
            action = await self._action_resolver(request, observation)
        elif metrics is not None:
            metrics.record_cache(hit=True)
        result = await self._action_executor(action, observation)
        action_name = action.name
        if source != "cache" and not result.get("error"):
            await self._cache_write(
                request,
                _cacheable_action(action, observation),
                observation,
                result,
            )
        if should_attempt_computer_use_fallback(result) and computer_use_enabled():
            fallback_action = await self._computer_use_fallback(
                request,
                observation,
                result,
            )
            if fallback_action is not None:
                execute = self._computer_use_execute or _default_computer_use_execute
                cu_result = await execute(
                    action=fallback_action,
                    reason="structured_action_failed",
                    allowed_domains=request.context.allowed_domains,
                    require_confirmation=request.context.require_confirmation,
                    emit=emit,
                    page_provider=self._page_provider,
                )
                if not cu_result.get("error"):
                    result = cu_result
                    source = "computer_use"
                    action_name = fallback_action.action
        await _maybe_emit(
            emit,
            {
                "event": "primitive_act",
                "instruction": request.instruction,
                "url": observation.url,
                "action": action_name,
                "source": source,
                "result": result,
            },
        )
        return ActResult(
            instruction=request.instruction,
            url=observation.url,
            action=action_name,
            result=result,
            source=source,
        )

    async def extract(
        self,
        request: ExtractRequest,
        *,
        emit: Optional[EmitFn] = None,
    ) -> ExtractResult:
        page = await self._page_provider()
        data = await self._extract(page, request.instruction, request.extraction_schema)
        valid = True
        error: Optional[str] = None
        if request.extraction_schema:
            valid, error = _validate_json_schema(data, request.extraction_schema)
            if valid:
                error = None
        await _maybe_emit(
            emit,
            {
                "event": "primitive_extract",
                "instruction": request.instruction,
                "valid": valid,
                "error": error,
            },
        )
        return ExtractResult(
            instruction=request.instruction,
            data=data,
            valid=valid,
            error=error,
        )

    async def agent_task(
        self,
        request: AgentTaskRequest,
        *,
        emit: Optional[EmitFn] = None,
    ) -> AgentTaskPrimitiveResult:
        async def forward(payload: dict[str, Any]) -> None:
            await _maybe_emit(emit, payload)

        spec = TaskSpec(
            objective=request.objective,
            start_url=request.start_url,
            max_steps=request.max_steps,
            max_seconds=request.max_seconds,
            success_criteria=request.success_criteria,
            allowed_domains=request.allowed_domains,
            data_schema=request.data_schema,
            require_confirmation=request.require_confirmation,
            allowed_tools=request.allowed_tools,
            synthesize_workflow=request.synthesize_workflow,
            session_memory=(
                await self._memory_loader(request.context.browser_session_id)
                if request.context.browser_session_id
                else None
            ),
        )
        result = await self._task_runner(spec, forward)
        if request.context.browser_session_id:
            await self._memory_appender(
                request.context.browser_session_id,
                request,
                result,
            )
        return AgentTaskPrimitiveResult(result=result)

    async def _execute_action(
        self,
        action: PrimitiveAction,
        observation: Observation,
    ) -> dict[str, Any]:
        page = await self._page_provider()
        if action.name == "click_element":
            index = int(action.args["index"])
            locator, _ = await resolve_element(page, observation, index)
            if locator is None:
                return {"error": f"index {index} unavailable"}
            await locator.click()
            return {"clicked_index": index, "url": getattr(page, "url", observation.url)}
        if action.name == "type_text":
            index = int(action.args["index"])
            text = str(action.args.get("text", ""))
            locator, _ = await resolve_element(page, observation, index)
            if locator is None:
                return {"error": f"index {index} unavailable"}
            await locator.fill(text)
            return {"typed_index": index, "text": text, "url": getattr(page, "url", observation.url)}
        if action.name == "wait":
            return {"waited_ms": int(action.args.get("ms", 500))}
        return {"error": f"unsupported primitive action {action.name!r}"}


__all__ = [
    "ActRequest",
    "ActResult",
    "AgentTaskPrimitiveResult",
    "AgentTaskRequest",
    "BrowserPrimitiveService",
    "ExtractRequest",
    "ExtractResult",
    "ObserveRequest",
    "ObserveResult",
    "PrimitiveAction",
    "PrimitiveCandidate",
    "PrimitiveContext",
]
