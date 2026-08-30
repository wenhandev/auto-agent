from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlmodel import Session, select

from app.db.crypto import decrypt, encrypt
from app.db.models import LlmConfig
from app.db.session import get_session
from app.schemas_api import (
    LlmConfigOut,
    LlmConfigUpsert,
    LlmEffectiveOut,
    ModelPriceEntry,
    ModelPricesOut,
    ModelPricesUpdate,
)
from app.services import llm_runtime


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/llm-config", tags=["llm-config"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_out(row: LlmConfig) -> LlmConfigOut:
    try:
        plain = decrypt(row.api_key_ciphertext).decode("utf-8")
    except Exception:
        plain = ""
    return LlmConfigOut(
        id=row.id,
        provider=row.provider,
        model=row.model,
        api_key_masked=llm_runtime.mask_api_key(plain),
        base_url=row.base_url,
        is_active=row.is_active,
        self_healing_enabled=bool(getattr(row, "self_healing_enabled", True)),
        self_healing_vision_threshold=float(
            getattr(row, "self_healing_vision_threshold", 0.6)
        ),
        selector_cache_enabled=bool(getattr(row, "selector_cache_enabled", True)),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[LlmConfigOut])
def list_configs(session: Session = Depends(get_session)) -> list[LlmConfigOut]:
    rows = session.exec(
        select(LlmConfig).order_by(LlmConfig.updated_at.desc())  # type: ignore[attr-defined]
    ).all()
    return [_to_out(r) for r in rows]


@router.get("/effective", response_model=LlmEffectiveOut)
def get_effective(session: Session = Depends(get_session)) -> LlmEffectiveOut:
    try:
        eff = llm_runtime.effective_settings(session)
    except RuntimeError:
        return LlmEffectiveOut(source="none")
    return LlmEffectiveOut(
        source=eff.source,  # type: ignore[arg-type]
        provider=eff.provider,
        model=eff.model,
        api_key_masked=llm_runtime.mask_api_key(eff.api_key),
        base_url=eff.base_url,
    )


@router.post("", response_model=LlmConfigOut)
def upsert_config(
    body: LlmConfigUpsert, session: Session = Depends(get_session)
) -> LlmConfigOut:
    others = session.exec(select(LlmConfig).where(LlmConfig.is_active == True)).all()  # noqa: E712
    for o in others:
        o.is_active = False
        o.updated_at = _utcnow()
        session.add(o)
    row = LlmConfig(
        provider=body.provider,
        model=body.model,
        api_key_ciphertext=encrypt(body.api_key.encode("utf-8")),
        base_url=body.base_url,
        is_active=True,
        self_healing_enabled=(
            True if body.self_healing_enabled is None else bool(body.self_healing_enabled)
        ),
        self_healing_vision_threshold=(
            0.6
            if body.self_healing_vision_threshold is None
            else float(body.self_healing_vision_threshold)
        ),
        selector_cache_enabled=(
            True
            if body.selector_cache_enabled is None
            else bool(body.selector_cache_enabled)
        ),
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    llm_runtime.invalidate_cache()
    return _to_out(row)


@router.put("", response_model=LlmConfigOut)
def upsert_config_put(
    body: LlmConfigUpsert, session: Session = Depends(get_session)
) -> LlmConfigOut:
    return upsert_config(body, session)


@router.post("/{config_id}/activate", response_model=LlmConfigOut)
def activate_config(
    config_id: str, session: Session = Depends(get_session)
) -> LlmConfigOut:
    target = session.get(LlmConfig, config_id)
    if target is None:
        raise HTTPException(404, detail="config not found")
    if not target.is_active:
        others = session.exec(
            select(LlmConfig).where(LlmConfig.is_active == True)  # noqa: E712
        ).all()
        for o in others:
            o.is_active = False
            o.updated_at = _utcnow()
            session.add(o)
        target.is_active = True
        target.updated_at = _utcnow()
        session.add(target)
        session.commit()
        session.refresh(target)
        llm_runtime.invalidate_cache()
    return _to_out(target)


@router.delete("/{config_id}")
def delete_config(
    config_id: str, session: Session = Depends(get_session)
) -> dict:
    row = session.get(LlmConfig, config_id)
    if row is None:
        raise HTTPException(404, detail="config not found")
    was_active = row.is_active
    session.delete(row)
    session.commit()
    if was_active:
        llm_runtime.invalidate_cache()
    return {"ok": True}


@router.get("/model-prices", response_model=ModelPricesOut)
def get_model_prices() -> ModelPricesOut:
    from app.services import cost_tracking as cost_svc

    prices = cost_svc.get_model_prices()
    return ModelPricesOut(
        prices={
            model: ModelPriceEntry(**rates)
            for model, rates in prices.items()
        }
    )


@router.put("/model-prices", response_model=ModelPricesOut)
def update_model_prices(body: ModelPricesUpdate) -> ModelPricesOut:
    from app.services import cost_tracking as cost_svc

    saved = cost_svc.save_model_prices(
        {model: entry.model_dump() for model, entry in body.prices.items()}
    )
    return ModelPricesOut(
        prices={
            model: ModelPriceEntry(**rates)
            for model, rates in saved.items()
        }
    )


@router.post("/test")
async def test_config(body: LlmConfigUpsert = Body(...)) -> dict:
    eff = llm_runtime.EffectiveLlmSettings(
        source="probe",
        id=None,
        provider=body.provider,
        model=body.model,
        api_key=body.api_key,
        base_url=body.base_url,
    )
    try:
        model = llm_runtime._build_model(eff)
    except Exception as exc:
        return {"ok": False, "error": f"build_model failed: {exc}"}

    try:
        from google.adk.agents import LlmAgent
        from google.adk.runners import Runner
        from google.adk.sessions.in_memory_session_service import InMemorySessionService
        from google.genai import types

        agent = LlmAgent(name="llm_test", model=model, instruction="Reply with the single word 'ok'.")
        svc = InMemorySessionService()
        runner = Runner(app_name="llm-test", agent=agent, session_service=svc)
        await svc.create_session(app_name="llm-test", user_id="t", session_id="t")
        msg = types.Content(role="user", parts=[types.Part(text="ping")])
        text = ""
        async for event in runner.run_async(user_id="t", session_id="t", new_message=msg):
            if event.is_final_response() and event.content and event.content.parts:
                for p in event.content.parts:
                    if getattr(p, "text", None):
                        text += p.text
        text = text.strip()
        if not text:
            return {"ok": False, "error": "model returned empty response"}
        return {"ok": True, "message": text[:200]}
    except Exception as exc:
        logger.exception("llm test call failed")
        return {"ok": False, "error": str(exc)}


__all__ = ["router"]
