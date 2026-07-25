from __future__ import annotations

from typing import Any

from auth import User
from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_app_state, get_current_user
from ..state import AppState

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _get_owned_job(job_id: str, state: AppState, current_user: User):
    """Phase 8 WP5 authorization review: these two routes previously had
    no `get_current_user` dependency at all - any caller, authenticated
    or not, could read any job's full render_spec/error detail by
    guessing or enumerating job ids. Fixed by requiring auth and
    checking the job's *owning project*'s `created_by`, the same
    ownership check every other project-scoped route already uses
    (`routes/projects.py`'s `_get_owned_project`) - `GenerationJob` has
    no owner of its own, only a `project_id`."""
    job = state.job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No such job: {job_id}")
    project = state.project_store.get(job.project_id)
    if project is None or project.created_by != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not the owner of this job")
    return job


@router.get("/{job_id}")
def get_job(
    job_id: str,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return _get_owned_job(job_id, state, current_user).to_dict()


@router.get("/{job_id}/status")
def get_job_status(
    job_id: str,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    job = _get_owned_job(job_id, state, current_user)
    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "retry_count": job.retry_count,
        "error_message": job.error_message,
    }
