from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any

from auth import User
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..dependencies import get_app_state, get_current_user
from ..state import AppState

router = APIRouter(prefix="/assets", tags=["assets"])

_READ_CHUNK_BYTES = 1024 * 1024


@router.post("/upload", status_code=201)
def upload_asset(
    file: UploadFile = File(...),
    project_id: str | None = Form(default=None),
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Uploads a reference image (or other input asset) ahead of/alongside
    project creation. Frontend flow: upload here first to get an
    asset_id, then pass it in `CreateProjectRequest.reference_asset_ids`.

    `project_id` is optional because reference images are commonly
    uploaded before a project exists yet - when omitted the asset is
    filed under the caller's workspace rather than a specific project.
    Ownership isn't separately checked against `project_id` here since
    this endpoint never reveals or mutates existing project data, only
    registers a new asset the caller is uploading themselves.

    Phase 8 WP5 (`docs/adr/0020-security-hardening.md`,
    `docs/PHASE8_SCALEOUT_PLAN.md` item 24): validates `Content-Type`
    against an allowlist and streams the body in bounded chunks rather
    than one unbounded `.read()` call, rejecting mid-stream the moment
    `upload_max_bytes` is exceeded - a single unbounded read was itself
    a memory-exhaustion vector regardless of any `Content-Length` the
    client claimed (a client can lie about it, or omit it).
    """
    if file.content_type not in state.upload_allowed_content_types:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported content type: {file.content_type!r}. "
            f"Allowed: {sorted(state.upload_allowed_content_types)}",
        )

    if project_id is not None:
        record = state.project_store.get(project_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"No such project: {project_id}")
        if record.created_by != current_user.user_id:
            raise HTTPException(status_code=403, detail="Not the owner of this project")

    suffix = Path(file.filename or "").suffix
    total_bytes = 0
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
        while chunk := file.file.read(_READ_CHUNK_BYTES):
            total_bytes += len(chunk)
            if total_bytes > state.upload_max_bytes:
                tmp.close()
                Path(tmp_path).unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"Upload exceeds the {state.upload_max_bytes}-byte limit",
                )
            tmp.write(chunk)

    try:
        key = f"{current_user.workspace_id}/{uuid.uuid4().hex}{suffix}"
        uri = state.asset_manager.persist_local_copy(key, tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    record = state.asset_manager.register(
        project_id=project_id or f"workspace:{current_user.workspace_id}",
        kind="image",
        uri=uri,
        metadata={"original_filename": file.filename, "content_type": file.content_type},
    )
    return record
