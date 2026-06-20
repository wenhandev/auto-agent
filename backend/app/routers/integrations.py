from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.integrations.registry import catalogue, get_descriptor

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


@router.get("")
def list_integrations() -> list[dict]:
    return [e.model_dump() for e in catalogue()]


@router.get("/{app}")
def get_integration(app: str) -> dict:
    try:
        desc = get_descriptor(app)
    except KeyError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    return desc.model_dump()


__all__ = ["router"]
