"""Expression preview endpoint for the safe evaluator."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

import app.services.expressions  # noqa: F401 — register evaluator with interpolation
from app.auth.context import AuthContext, get_org_context, require_org_match
from app.db.models import Workflow
from app.db.session import get_session
from app.schemas_api import ExpressionPreviewRequest, ExpressionPreviewResponse
from app.services.expressions import ExpressionError, evaluate
from app.services.last_output_shapes import (
    fetch_last_output_shapes,
    preview_context_from_shapes,
)


router = APIRouter(prefix="/api/expressions", tags=["expressions"])


def _normalize_expression(raw: str) -> str:
    text = raw.strip()
    if text.startswith("{{=") and text.endswith("}}"):
        return text[3:-2].strip()
    if text.startswith("{{") and text.endswith("}}"):
        inner = text[2:-2].strip()
        if inner.startswith("="):
            return inner[1:].strip()
    return text


def _resolve_preview_namespace(
    body: ExpressionPreviewRequest,
    session: Session,
    ctx: AuthContext,
) -> dict[str, Any] | ExpressionPreviewResponse:
    namespace: dict[str, Any] = dict(body.context or {})
    if not body.workflow_id or "nodes" in namespace:
        return namespace

    workflow = session.get(Workflow, body.workflow_id)
    if workflow is None:
        raise HTTPException(404, detail="workflow not found")
    require_org_match(workflow.org_id, ctx.org_id, session)

    shapes = fetch_last_output_shapes(session, body.workflow_id)
    if not shapes.shapes:
        return ExpressionPreviewResponse(
            ok=False,
            type=None,
            value=None,
            error="no run data",
        )
    namespace.update(preview_context_from_shapes(shapes.shapes))
    return namespace


@router.post("/preview", response_model=ExpressionPreviewResponse)
def preview_expression(
    body: ExpressionPreviewRequest,
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> ExpressionPreviewResponse:
    expr = _normalize_expression(body.expression)
    namespace_or_error = _resolve_preview_namespace(body, session, ctx)
    if isinstance(namespace_or_error, ExpressionPreviewResponse):
        return namespace_or_error
    namespace = namespace_or_error
    try:
        result = evaluate(expr, namespace)
        return ExpressionPreviewResponse(
            ok=True,
            type=type(result).__name__,
            value=result,
            error=None,
        )
    except ExpressionError as exc:
        return ExpressionPreviewResponse(
            ok=False,
            type=None,
            value=None,
            error=str(exc),
        )


__all__ = ["router"]
