from __future__ import annotations

import importlib.util
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.integrations.auth import RenderedRequest
from app.integrations.schema import Operation

logger = logging.getLogger(__name__)

_INTEGRATIONS_ROOT = Path(__file__).resolve().parent

BeforeRequestHook = Callable[
    [str, str, str, RenderedRequest, dict[str, Any]],
    Awaitable[None] | None,
]
CheckResponseHook = Callable[[str, str, str, dict[str, Any]], None]
MapItemsHook = Callable[
    [str, str, str, dict[str, Any], Operation, dict[str, Any], list[dict[str, Any]]],
    list[dict[str, Any]] | None,
]


@dataclass
class AppHooks:
    before_request: BeforeRequestHook | None = None
    check_response: CheckResponseHook | None = None
    map_items: MapItemsHook | None = None


_hooks: dict[str, AppHooks] = {}
_loaded = False


def register_hooks(app: str, hooks: AppHooks) -> None:
    _hooks[app] = hooks


def get_hooks(app: str) -> AppHooks | None:
    return _hooks.get(app)


def _load_custom_module(app_dir: Path) -> Any | None:
    custom_path = app_dir / "custom.py"
    if not custom_path.exists():
        return None
    spec = importlib.util.spec_from_file_location(
        f"integration_custom_{app_dir.name}", custom_path
    )
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _hooks_from_module(mod: Any) -> AppHooks:
    return AppHooks(
        before_request=getattr(mod, "before_request", None),
        check_response=getattr(mod, "check_response", None),
        map_items=getattr(mod, "map_items", None),
    )


def load_app_hooks(root: Path | None = None) -> None:
    global _loaded
    base = root or _INTEGRATIONS_ROOT
    for child in sorted(base.iterdir()):
        if not child.is_dir() or child.name == "__pycache__":
            continue
        if child.name.startswith("_"):
            continue
        mod = _load_custom_module(child)
        if mod is None:
            continue
        hooks = _hooks_from_module(mod)
        if any((hooks.before_request, hooks.check_response, hooks.map_items)):
            register_hooks(child.name, hooks)
            logger.info("loaded integration hooks app=%s", child.name)


def reset_hooks() -> None:
    global _loaded
    _hooks.clear()
    _loaded = False


__all__ = [
    "AppHooks",
    "BeforeRequestHook",
    "CheckResponseHook",
    "MapItemsHook",
    "get_hooks",
    "load_app_hooks",
    "register_hooks",
    "reset_hooks",
]
