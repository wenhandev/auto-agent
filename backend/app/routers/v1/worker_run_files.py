"""Worker-authenticated access to run input files."""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.auth.worker_auth import WorkerAuth, require_worker_session
from app.db.models import Run
from app.db.session import get_session
from app.services import run_inputs as run_input_svc


router = APIRouter(prefix="/workers", tags=["workers"])


@router.get("/runs/{run_id}/input-files/{file_id}")
def worker_fetch_run_input_file(
    run_id: str,
    file_id: str,
    session: Session = Depends(get_session),
    auth: WorkerAuth = Depends(require_worker_session),
):
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    if run.org_id and run.org_id != auth.worker.org_id:
        raise HTTPException(status_code=403, detail="run not in worker org")
    if run.worker_id and run.worker_id != auth.worker.id:
        raise HTTPException(status_code=403, detail="run assigned to another worker")

    path = run_input_svc.resolve_run_input_file(run_id, file_id)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="input file not found")
    filename = path.name.split("_", 1)[-1] if "_" in path.name else path.name
    guessed, _ = mimetypes.guess_type(filename)
    return FileResponse(
        path=path,
        media_type=guessed or "application/octet-stream",
        filename=filename,
    )


__all__ = ["router"]
