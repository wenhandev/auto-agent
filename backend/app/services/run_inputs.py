"""Staging and run-scoped input files for workflow file parameters."""

from __future__ import annotations

import json
import logging
import mimetypes
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, BinaryIO, Optional

from app.schemas import WorkflowParameter
from app.settings import settings
from app.tools.sandbox import resolve_sandbox_path, workflow_dir


logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_default_staging_root = _BACKEND_ROOT / "data" / "run_input_staging"
_default_run_inputs_root = _BACKEND_ROOT / "data" / "run_inputs"
_staging_root: Path = _default_staging_root
_run_inputs_root: Path = _default_run_inputs_root

_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


class RunInputError(ValueError):
    """Raised when a run input file operation fails validation."""


def set_staging_root(path: Path) -> None:
    global _staging_root
    _staging_root = path


def set_run_inputs_root(path: Path) -> None:
    global _run_inputs_root
    _run_inputs_root = path


def reset_roots() -> None:
    global _staging_root, _run_inputs_root
    _staging_root = _default_staging_root
    _run_inputs_root = _default_run_inputs_root


def ensure_roots() -> None:
    _staging_root.mkdir(parents=True, exist_ok=True)
    _run_inputs_root.mkdir(parents=True, exist_ok=True)


def _sanitize_filename(name: str) -> str:
    base = Path(name).name or "upload.bin"
    cleaned = _SAFE_NAME_RE.sub("_", base).strip("._")
    return cleaned or "upload.bin"


def _guess_content_type(filename: str) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def _staging_dir(workflow_id: str, file_id: str) -> Path:
    return _staging_root / workflow_id / file_id


def _run_input_path(run_id: str, file_id: str, filename: str) -> Path:
    safe = _sanitize_filename(filename)
    return _run_inputs_root / run_id / f"{file_id}_{safe}"


def store_staging_file(
    workflow_id: str,
    data: bytes,
    *,
    filename: str,
    content_type: Optional[str] = None,
) -> dict[str, Any]:
    """Persist an uploaded file before run creation; returns staging metadata."""
    if len(data) > settings.max_artifact_bytes:
        raise RunInputError(
            f"file exceeds max size ({settings.max_artifact_bytes} bytes)"
        )
    if not data:
        raise RunInputError("empty file upload")

    ensure_roots()
    file_id = str(uuid.uuid4())
    safe_name = _sanitize_filename(filename)
    dest_dir = _staging_dir(workflow_id, file_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / safe_name
    dest_path.write_bytes(data)

    return {
        "file_id": file_id,
        "filename": safe_name,
        "content_type": content_type or _guess_content_type(safe_name),
        "bytes": len(data),
    }


def store_staging_upload(
    workflow_id: str,
    stream: BinaryIO,
    *,
    filename: str,
    content_type: Optional[str] = None,
) -> dict[str, Any]:
    data = stream.read()
    return store_staging_file(
        workflow_id,
        data,
        filename=filename,
        content_type=content_type,
    )


def get_staging_file(workflow_id: str, file_id: str) -> Optional[Path]:
    base = _staging_dir(workflow_id, file_id)
    if not base.is_dir():
        return None
    files = [p for p in base.iterdir() if p.is_file()]
    if not files:
        return None
    return files[0]


def resolve_run_input_file(run_id: str, file_id: str) -> Optional[Path]:
    run_dir = _run_inputs_root / run_id
    if not run_dir.is_dir():
        return None
    prefix = f"{file_id}_"
    for path in run_dir.iterdir():
        if path.is_file() and path.name.startswith(prefix):
            return path
    return None


def list_run_input_files(run_id: str) -> list[dict[str, Any]]:
    run_dir = _run_inputs_root / run_id
    if not run_dir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(run_dir.iterdir()):
        if not path.is_file():
            continue
        name = path.name
        if "_" not in name:
            continue
        file_id, filename = name.split("_", 1)
        out.append(
            {
                "file_id": file_id,
                "filename": filename,
                "bytes": path.stat().st_size,
                "content_type": _guess_content_type(filename),
            }
        )
    return out


def parse_file_param_ref(raw: Any) -> str:
    """Validate a file parameter value and return the staging file_id."""
    return _coerce_file_ref(raw)


def _coerce_file_ref(raw: Any) -> str:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, dict):
        file_id = raw.get("file_id")
        if isinstance(file_id, str) and file_id.strip():
            return file_id.strip()
    raise RunInputError("file parameter expects {file_id: ...} or a file_id string")


def materialize_file_parameters(
    workflow_id: str,
    run_id: str,
    resolved: dict[str, Any],
    declared: list[WorkflowParameter],
) -> dict[str, Any]:
    """Copy staging files into run storage and workflow sandbox; update param values."""
    file_params = [p for p in declared if p.type == "file"]
    if not file_params:
        return resolved

    out = dict(resolved)
    ensure_roots()
    inputs_dir = workflow_dir(workflow_id) / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    run_dir = _run_inputs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    for param in file_params:
        if param.name not in out:
            continue
        file_id = _coerce_file_ref(out[param.name])
        staging_path = get_staging_file(workflow_id, file_id)
        if staging_path is None:
            raise RunInputError(
                f"staging file {file_id!r} not found for parameter {param.name!r}"
            )

        filename = staging_path.name
        data = staging_path.read_bytes()
        run_copy = _run_input_path(run_id, file_id, filename)
        if not run_copy.is_file():
            shutil.copy2(staging_path, run_copy)

        sandbox_rel = f"inputs/{file_id[:8]}_{filename}"
        sandbox_path = resolve_sandbox_path(sandbox_rel, workflow_id=workflow_id)
        sandbox_path.parent.mkdir(parents=True, exist_ok=True)
        sandbox_path.write_bytes(data)

        out[param.name] = {
            "file_id": file_id,
            "filename": filename,
            "path": sandbox_rel,
            "content_type": _guess_content_type(filename),
            "bytes": len(data),
        }

    return out


def mask_file_parameters(
    resolved: dict[str, Any],
    declared: list[WorkflowParameter],
) -> dict[str, Any]:
    file_names = {p.name for p in declared if p.type == "file"}
    out: dict[str, Any] = {}
    for key, value in resolved.items():
        if key in file_names and isinstance(value, dict):
            out[key] = {
                "filename": value.get("filename"),
                "path": value.get("path"),
                "bytes": value.get("bytes"),
                "content_type": value.get("content_type"),
            }
        else:
            out[key] = value
    return out


def load_input_files_for_worker(run_id: str, resolved: dict[str, Any]) -> list[dict[str, Any]]:
    """Build input file descriptors for worker execute_run payload."""
    files: list[dict[str, Any]] = []
    for key, value in resolved.items():
        if not isinstance(value, dict):
            continue
        file_id = value.get("file_id")
        path = value.get("path")
        filename = value.get("filename")
        if not isinstance(file_id, str) or not isinstance(path, str):
            continue
        files.append(
            {
                "param": key,
                "file_id": file_id,
                "path": path,
                "filename": filename or Path(path).name,
                "content_type": value.get("content_type"),
                "bytes": value.get("bytes"),
            }
        )
    if not files:
        files = [
            {
                "param": item["file_id"],
                "file_id": item["file_id"],
                "filename": item["filename"],
                "path": f"inputs/{item['filename']}",
                "content_type": item.get("content_type"),
                "bytes": item.get("bytes"),
            }
            for item in list_run_input_files(run_id)
        ]
    return files


__all__ = [
    "RunInputError",
    "ensure_roots",
    "get_staging_file",
    "list_run_input_files",
    "load_input_files_for_worker",
    "mask_file_parameters",
    "parse_file_param_ref",
    "materialize_file_parameters",
    "reset_roots",
    "resolve_run_input_file",
    "set_run_inputs_root",
    "set_staging_root",
    "store_staging_file",
    "store_staging_upload",
]
