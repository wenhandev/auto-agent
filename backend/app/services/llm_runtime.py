from __future__ import annotations

import logging
from dataclasses import dataclass
from threading import Lock
from typing import Any, Optional, Union

from sqlmodel import Session, select

from app.db.crypto import decrypt
from app.db.models import LlmConfig
from app.db.session import engine
from app.settings import settings


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EffectiveLlmSettings:
    source: str
    id: Optional[str]
    provider: str
    model: str
    api_key: str
    base_url: Optional[str]


_cached_fingerprint: Optional[tuple] = None
_cached_model: Any = None

_self_heal_lock = Lock()
_cached_self_heal_fp: Optional[tuple] = None
_cached_self_heal: Optional[dict] = None


@dataclass(frozen=True)
class SelfHealSettings:
    enabled: bool
    threshold: float


@dataclass(frozen=True)
class SelectorCacheSettings:
    enabled: bool


_cached_selector_cache_fp: Optional[tuple] = None
_cached_selector_cache: Optional[dict] = None


def _env_settings() -> Optional[EffectiveLlmSettings]:
    provider = (settings.llm_provider or "").lower() or None
    if provider in ("google", "gemini"):
        if settings.gemini_provider.lower() == "vertex" and settings.gcp_project:
            return EffectiveLlmSettings(
                source="env",
                id=None,
                provider="google",
                model=settings.google_model,
                api_key="",
                base_url=settings.google_base_url,
            )
        if not settings.google_api_key:
            return None
        return EffectiveLlmSettings(
            source="env",
            id=None,
            provider="google",
            model=settings.google_model,
            api_key=settings.google_api_key,
            base_url=settings.google_base_url,
        )
    if provider == "openai":
        if not settings.openai_api_key:
            return None
        return EffectiveLlmSettings(
            source="env",
            id=None,
            provider="openai",
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
    return None


def _db_settings(session: Session) -> Optional[EffectiveLlmSettings]:
    row = session.exec(
        select(LlmConfig).where(LlmConfig.is_active == True)  # noqa: E712
    ).first()
    if row is None:
        return None
    if not row.provider or not row.model or not row.api_key_ciphertext:
        logger.warning(
            "LlmConfig %s missing required fields (provider/model/api_key_ciphertext); "
            "falling back to .env in full",
            row.id,
        )
        return None
    try:
        plain = decrypt(row.api_key_ciphertext).decode("utf-8")
    except Exception:
        logger.exception("LlmConfig %s api key decryption failed; refusing row", row.id)
        return None
    return EffectiveLlmSettings(
        source="db",
        id=row.id,
        provider=row.provider,
        model=row.model,
        api_key=plain,
        base_url=row.base_url,
    )


def effective_settings(session: Optional[Session] = None) -> EffectiveLlmSettings:
    if session is None:
        with Session(engine) as own:
            db = _db_settings(own)
    else:
        db = _db_settings(session)
    if db is not None:
        return db
    env = _env_settings()
    if env is not None:
        return env
    raise RuntimeError(
        "No LLM configuration available: no active LlmConfig row and .env has no usable provider key"
    )


def mask_api_key(plain: str) -> str:
    if not plain:
        return ""
    tail = plain[-4:] if len(plain) >= 4 else plain
    return f"***{tail}"


def _fingerprint(eff: EffectiveLlmSettings) -> tuple:
    return (eff.provider, eff.model, eff.base_url, eff.api_key)


def _build_model(eff: EffectiveLlmSettings):
    from google.adk.models.lite_llm import LiteLlm

    if eff.provider in ("google", "gemini"):
        if (
            settings.gemini_provider.lower() == "vertex"
            and settings.gcp_project
            and not eff.base_url
        ):
            from app.agents.model import _VertexGemini

            return _VertexGemini(model=eff.model)
        if eff.base_url:
            from app.agents.model import _RelayGemini

            return _RelayGemini(
                model=eff.model,
                base_url=eff.base_url,
                api_key=eff.api_key,
            )
        return eff.model
    if eff.provider == "openai":
        kwargs: dict[str, Any] = {"model": f"openai/{eff.model}"}
        if eff.base_url:
            kwargs["api_base"] = eff.base_url
        if eff.api_key:
            kwargs["api_key"] = eff.api_key
        return LiteLlm(**kwargs)
    raise ValueError(f"Unknown provider {eff.provider!r}")


def get_active_model() -> Union[str, Any]:
    global _cached_fingerprint, _cached_model
    eff = effective_settings()
    fp = _fingerprint(eff)
    if _cached_fingerprint == fp and _cached_model is not None:
        return _cached_model
    model = _build_model(eff)
    _cached_fingerprint = fp
    _cached_model = model
    return model


def invalidate_cache() -> None:
    global _cached_fingerprint, _cached_model, _cached_self_heal_fp, _cached_self_heal
    global _cached_selector_cache_fp, _cached_selector_cache
    _cached_fingerprint = None
    _cached_model = None
    with _self_heal_lock:
        _cached_self_heal_fp = None
        _cached_self_heal = None
        _cached_selector_cache_fp = None
        _cached_selector_cache = None


def get_self_heal_settings(
    session: Optional[Session] = None,
) -> SelfHealSettings:
    """Return the active `LlmConfig`'s self-healing toggle + vision threshold.

    Falls back to the documented defaults (`enabled=True`, `threshold=0.6`)
    when no active `LlmConfig` row exists (.env-only setup). Cached using the
    same invalidation hook as `get_active_model()` so activating a different
    config rotates both values together.
    """
    global _cached_self_heal_fp, _cached_self_heal

    def _read(own_session: Session) -> SelfHealSettings:
        row = own_session.exec(
            select(LlmConfig).where(LlmConfig.is_active == True)  # noqa: E712
        ).first()
        if row is None:
            return SelfHealSettings(enabled=True, threshold=0.6)
        enabled = bool(getattr(row, "self_healing_enabled", True))
        threshold = float(getattr(row, "self_healing_vision_threshold", 0.6))
        threshold = max(0.0, min(1.0, threshold))
        return SelfHealSettings(enabled=enabled, threshold=threshold)

    if session is None:
        with Session(engine) as own:
            row = own.exec(
                select(LlmConfig).where(LlmConfig.is_active == True)  # noqa: E712
            ).first()
            fp = (
                (row.id, row.self_healing_enabled, row.self_healing_vision_threshold)
                if row is not None
                else (None, True, 0.6)
            )
            with _self_heal_lock:
                if _cached_self_heal_fp == fp and _cached_self_heal is not None:
                    return SelfHealSettings(**_cached_self_heal)
                result = _read(own)
                _cached_self_heal_fp = fp
                _cached_self_heal = {
                    "enabled": result.enabled,
                    "threshold": result.threshold,
                }
                return result

    return _read(session)


def get_selector_cache_settings(
    session: Optional[Session] = None,
) -> SelectorCacheSettings:
    """Return whether selector/action cache is enabled (default on)."""
    global _cached_selector_cache_fp, _cached_selector_cache

    def _read(own_session: Session) -> SelectorCacheSettings:
        row = own_session.exec(
            select(LlmConfig).where(LlmConfig.is_active == True)  # noqa: E712
        ).first()
        if row is None:
            return SelectorCacheSettings(enabled=True)
        return SelectorCacheSettings(
            enabled=bool(getattr(row, "selector_cache_enabled", True))
        )

    if session is None:
        with Session(engine) as own:
            row = own.exec(
                select(LlmConfig).where(LlmConfig.is_active == True)  # noqa: E712
            ).first()
            fp = (row.id, getattr(row, "selector_cache_enabled", True)) if row else (None, True)
            with _self_heal_lock:
                if _cached_selector_cache_fp == fp and _cached_selector_cache is not None:
                    return SelectorCacheSettings(**_cached_selector_cache)
                result = _read(own)
                _cached_selector_cache_fp = fp
                _cached_selector_cache = {"enabled": result.enabled}
                return result

    return _read(session)


__all__ = [
    "EffectiveLlmSettings",
    "SelfHealSettings",
    "SelectorCacheSettings",
    "effective_settings",
    "get_active_model",
    "get_self_heal_settings",
    "get_selector_cache_settings",
    "invalidate_cache",
    "mask_api_key",
]
