from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

from app.integrations.credential_types import register_credential_type
from app.integrations.hooks import load_app_hooks

logger = logging.getLogger(__name__)

_INTEGRATIONS_ROOT = Path(__file__).resolve().parent


def _load_credential_module(app_dir: Path) -> None:
    cred_path = app_dir / "credential.py"
    if not cred_path.exists():
        return
    spec = importlib.util.spec_from_file_location(
        f"integration_cred_{app_dir.name}", cred_path
    )
    if spec is None or spec.loader is None:
        return
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    register = getattr(mod, "register", None)
    if callable(register):
        register()
        return
    for name in dir(mod):
        obj = getattr(mod, name)
        if name.endswith("_TYPE") and hasattr(obj, "type"):
            register_credential_type(obj)


def bootstrap_integrations() -> None:
    for child in sorted(_INTEGRATIONS_ROOT.iterdir()):
        if not child.is_dir() or child.name == "__pycache__":
            continue
        if child.name.startswith("_"):
            continue
        _load_credential_module(child)
    load_app_hooks()


__all__ = ["bootstrap_integrations"]
