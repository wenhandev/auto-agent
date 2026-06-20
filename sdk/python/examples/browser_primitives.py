"""Example: hybrid browser primitives via the in-process service layer.

These helpers mirror the observe / act / extract / agent_task contracts used by
autonomous runs. Wire them to a live Playwright page in your integration tests
or scripts.
"""

from __future__ import annotations

from typing import Any, Optional

from app.services.browser_primitives import (
    ActRequest,
    AgentTaskRequest,
    BrowserPrimitiveService,
    ExtractRequest,
    ObserveRequest,
    PrimitiveContext,
)


async def observe_page(
    page: Any,
    instruction: str,
    *,
    run_id: Optional[str] = None,
) -> dict[str, Any]:
    service = BrowserPrimitiveService(page_provider=lambda: page)
    result = await service.observe(
        ObserveRequest(
            instruction=instruction,
            context=PrimitiveContext(run_id=run_id),
        )
    )
    return result.model_dump()


async def act_on_page(
    page: Any,
    instruction: str,
    *,
    run_id: Optional[str] = None,
    browser_session_id: Optional[str] = None,
) -> dict[str, Any]:
    service = BrowserPrimitiveService(page_provider=lambda: page)
    result = await service.act(
        ActRequest(
            instruction=instruction,
            context=PrimitiveContext(
                run_id=run_id,
                browser_session_id=browser_session_id,
            ),
        )
    )
    return result.model_dump()


async def extract_from_page(
    page: Any,
    instruction: str,
    schema: Optional[dict[str, Any]] = None,
    *,
    run_id: Optional[str] = None,
) -> dict[str, Any]:
    service = BrowserPrimitiveService(page_provider=lambda: page)
    result = await service.extract(
        ExtractRequest(
            instruction=instruction,
            extraction_schema=schema,
            context=PrimitiveContext(run_id=run_id),
        )
    )
    return result.model_dump()


async def run_agent_task(
    page: Any,
    objective: str,
    *,
    start_url: Optional[str] = None,
    browser_session_id: Optional[str] = None,
) -> dict[str, Any]:
    service = BrowserPrimitiveService(page_provider=lambda: page)
    result = await service.agent_task(
        AgentTaskRequest(
            objective=objective,
            start_url=start_url,
            context=PrimitiveContext(browser_session_id=browser_session_id),
        )
    )
    return result.model_dump()
