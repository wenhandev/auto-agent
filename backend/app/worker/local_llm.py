"""Local LLM configuration for desktop sidecar runs."""

from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.settings import settings


logger = logging.getLogger(__name__)

WORKER_DIR = Path.home() / ".auto-agent-worker"
LLM_CONFIG_FILE = WORKER_DIR / "llm.json"
LLM_KEY_FILE = WORKER_DIR / ".key"

_fernet: Fernet | None = None


def _restrict_perms(path: Path) -> None:
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError as exc:
        logger.warning("could not chmod %s to 0600: %s", path, exc)


def _load_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet
    WORKER_DIR.mkdir(parents=True, exist_ok=True)
    if LLM_KEY_FILE.is_file():
        key_bytes = LLM_KEY_FILE.read_bytes().strip()
    else:
        key_bytes = Fernet.generate_key()
        LLM_KEY_FILE.write_bytes(key_bytes)
        _restrict_perms(LLM_KEY_FILE)
        logger.info("generated machine-local LLM key at %s", LLM_KEY_FILE)
    _fernet = Fernet(key_bytes)
    return _fernet


def _read_plain_json(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def load_config() -> dict[str, Any]:
    if not LLM_CONFIG_FILE.is_file():
        return {}
    raw = LLM_CONFIG_FILE.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    if raw.startswith("gAAAA"):
        try:
            decrypted = _load_fernet().decrypt(raw.encode("utf-8"))
            data = json.loads(decrypted.decode("utf-8"))
        except (InvalidToken, json.JSONDecodeError, ValueError):
            logger.warning("failed to decrypt %s", LLM_CONFIG_FILE)
            return {}
        return data if isinstance(data, dict) else {}
    return _read_plain_json(raw)


def save_config(payload: dict[str, Any]) -> dict[str, Any]:
    WORKER_DIR.mkdir(parents=True, exist_ok=True)
    token = _load_fernet().encrypt(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("utf-8")
    LLM_CONFIG_FILE.write_text(token, encoding="utf-8")
    _restrict_perms(LLM_CONFIG_FILE)
    return payload


def public_config() -> dict[str, Any]:
    cfg = load_config()
    masked = dict(cfg)
    for key in ("openai_api_key", "google_api_key"):
        val = masked.get(key)
        if isinstance(val, str) and val:
            tail = val[-4:] if len(val) >= 4 else val
            masked[key] = f"***{tail}"
    return masked


def is_configured() -> bool:
    cfg = load_config()
    provider = str(cfg.get("llm_provider") or settings.llm_provider or "openai").lower()
    if provider == "openai":
        return bool(cfg.get("openai_api_key") or settings.openai_api_key)
    if provider in ("google", "gemini"):
        gemini_provider = str(cfg.get("gemini_provider") or settings.gemini_provider).lower()
        if gemini_provider == "vertex":
            return bool(cfg.get("gcp_project") or settings.gcp_project)
        return bool(cfg.get("google_api_key") or settings.google_api_key)
    return False


def apply_local_config() -> None:
    """Push saved desktop LLM settings into app.settings for local runs."""
    from app.services import llm_runtime

    cfg = load_config()
    if cfg.get("llm_provider"):
        settings.llm_provider = str(cfg["llm_provider"])
    if cfg.get("openai_api_key"):
        settings.openai_api_key = str(cfg["openai_api_key"])
    if cfg.get("openai_model"):
        settings.openai_model = str(cfg["openai_model"])
    if cfg.get("openai_base_url") is not None:
        settings.openai_base_url = cfg.get("openai_base_url") or None
    if cfg.get("google_api_key"):
        settings.google_api_key = str(cfg["google_api_key"])
    if cfg.get("google_model"):
        settings.google_model = str(cfg["google_model"])
    if cfg.get("google_base_url") is not None:
        settings.google_base_url = cfg.get("google_base_url") or None
    if cfg.get("gemini_provider"):
        settings.gemini_provider = str(cfg["gemini_provider"])
    if cfg.get("gcp_project"):
        settings.gcp_project = str(cfg["gcp_project"])
    if cfg.get("gcp_location"):
        settings.gcp_location = str(cfg["gcp_location"])

    if settings.gemini_provider.lower() == "vertex" and settings.gcp_project:
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
        os.environ["GOOGLE_CLOUD_PROJECT"] = settings.gcp_project
        os.environ["GOOGLE_CLOUD_LOCATION"] = settings.gcp_location

    llm_runtime.invalidate_cache()


def require_configured() -> None:
    apply_local_config()
    if not is_configured():
        raise RuntimeError(
            "Local LLM is not configured. Open Desktop Settings and set provider, model, and API key."
        )


__all__ = [
    "LLM_CONFIG_FILE",
    "LLM_KEY_FILE",
    "apply_local_config",
    "is_configured",
    "load_config",
    "public_config",
    "require_configured",
    "save_config",
]
