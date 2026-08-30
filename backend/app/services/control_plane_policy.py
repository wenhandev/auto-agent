"""Cloud control-plane policy: edge-only features are disabled on the web backend."""

from __future__ import annotations

from fastapi import HTTPException

from app.settings import settings

_EDGE_ONLY_MESSAGES: dict[str, str] = {
    "credentials": (
        "Credentials are stored on the desktop client or worker only, not in cloud storage."
    ),
    "workflows.create": (
        "Create workflows in the desktop client, then publish to the cloud."
    ),
    "recordings": "Recordings are only available on the desktop client.",
    "browser_sessions": "Browser sessions are only available on the desktop client.",
    "browser_profiles": "Browser profiles are only available on the desktop client.",
}


def is_control_plane() -> bool:
    return settings.execution_backend == "control_plane_only"


def require_edge_execution(feature: str) -> None:
    """Reject when the cloud backend must not host edge-local features."""
    if not is_control_plane():
        return
    detail = _EDGE_ONLY_MESSAGES.get(
        feature,
        f"{feature} is only available on the desktop client or worker.",
    )
    raise HTTPException(status_code=403, detail=detail)


__all__ = ["is_control_plane", "require_edge_execution"]
