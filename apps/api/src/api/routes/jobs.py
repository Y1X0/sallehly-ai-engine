from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_app_state
from ..state import AppState

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _get_job(job_id: str, state: AppState):
    job = state.job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No such job: {job_id}")
    return job


@router.get("/{job_id}")
def get_job(job_id: str, state: AppState = Depends(get_app_state)) -> dict[str, Any]:
    return _get_job(job_id, state).to_dict()


@router.get("/{job_id}/status")
def get_job_status(job_id: str, state: AppState = Depends(get_app_state)) -> dict[str, Any]:
    job = _get_job(job_id, state)
    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "retry_count": job.retry_count,
        "error_message": job.error_message,
    }
