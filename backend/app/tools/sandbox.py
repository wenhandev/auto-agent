"""Per-workflow filesystem sandbox for read_file / write_file nodes."""
from __future__ import annotations

import os
from pathlib import Path


class SandboxViolation(Exception):
    """Raised when a path escapes the per-workflow sandbox."""


_BACKEND_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_DIR = (_BACKEND_ROOT / "data" / "workflow_files").resolve()


def workflow_dir(workflow_id: str) -> Path:
    wf_dir = (WORKSPACE_DIR / workflow_id).resolve()
    prefix = str(WORKSPACE_DIR) + os.sep
    if not str(wf_dir).startswith(prefix) and wf_dir != WORKSPACE_DIR:
        raise SandboxViolation(f"invalid workflow_id for sandbox: {workflow_id!r}")
    wf_dir.mkdir(parents=True, exist_ok=True)
    return wf_dir


def resolve_sandbox_path(user_path: str, *, workflow_id: str) -> Path:
    if Path(user_path).is_absolute():
        raise SandboxViolation("absolute paths refused")
    base = workflow_dir(workflow_id)
    resolved = (base / user_path).resolve()
    prefix = str(base) + os.sep
    if not str(resolved).startswith(prefix) and resolved != base:
        raise SandboxViolation(
            f"path escapes workspace for workflow {workflow_id}: {user_path}"
        )
    return resolved


def ensure_workspace_root() -> None:
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)


__all__ = [
    "SandboxViolation",
    "WORKSPACE_DIR",
    "ensure_workspace_root",
    "resolve_sandbox_path",
    "workflow_dir",
]
