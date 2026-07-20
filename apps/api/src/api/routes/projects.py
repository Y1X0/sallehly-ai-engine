from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from render_orchestrator import ProjectLifecycleError

from ..dependencies import get_app_state
from ..state import AppState

router = APIRouter(prefix="/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    workspace_id: str
    created_by: str
    prompt: str
    target_duration_sec: float = Field(gt=0)
    aspect_ratio: str
    reference_asset_ids: list[str] | None = None
    style_preset_id: str | None = None


class RejectStoryboardRequest(BaseModel):
    feedback: list[str]


class RejectRenderRequest(BaseModel):
    feedback: list[str]
    quality_tier: str | None = None


def _run(fn: Callable[..., Any], *args: Any) -> dict[str, Any]:
    try:
        record = fn(*args)
    except ProjectLifecycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return record.to_dict()


@router.post("", status_code=201)
def create_project(body: CreateProjectRequest, state: AppState = Depends(get_app_state)) -> dict[str, Any]:
    return _run(
        state.orchestrator.create_project,
        body.workspace_id,
        body.created_by,
        body.prompt,
        body.target_duration_sec,
        body.aspect_ratio,
        body.reference_asset_ids,
        body.style_preset_id,
    )


@router.get("/{project_id}")
def get_project(project_id: str, state: AppState = Depends(get_app_state)) -> dict[str, Any]:
    record = state.project_store.get(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No such project: {project_id}")
    return record.to_dict()


@router.post("/{project_id}/generate-plan")
def generate_plan(project_id: str, state: AppState = Depends(get_app_state)) -> dict[str, Any]:
    return _run(state.orchestrator.generate_creative_plan, project_id)


@router.post("/{project_id}/approve-storyboard")
def approve_storyboard(project_id: str, state: AppState = Depends(get_app_state)) -> dict[str, Any]:
    return _run(state.orchestrator.approve_storyboard, project_id)


@router.post("/{project_id}/reject-storyboard")
def reject_storyboard(
    project_id: str, body: RejectStoryboardRequest, state: AppState = Depends(get_app_state)
) -> dict[str, Any]:
    return _run(state.orchestrator.reject_storyboard, project_id, body.feedback)


@router.post("/{project_id}/approve-render")
def approve_render(project_id: str, state: AppState = Depends(get_app_state)) -> dict[str, Any]:
    return _run(state.orchestrator.approve_render_plan, project_id)


@router.post("/{project_id}/reject-render")
def reject_render(
    project_id: str, body: RejectRenderRequest, state: AppState = Depends(get_app_state)
) -> dict[str, Any]:
    return _run(state.orchestrator.reject_render_plan, project_id, body.feedback, body.quality_tier)


@router.post("/{project_id}/generate-video")
def generate_video(project_id: str, state: AppState = Depends(get_app_state)) -> dict[str, Any]:
    return _run(state.orchestrator.generate_video, project_id)


@router.get("/{project_id}/assets")
def list_assets(project_id: str, state: AppState = Depends(get_app_state)) -> dict[str, Any]:
    record = state.project_store.get(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No such project: {project_id}")
    assets = [state.asset_manager.get(asset_id) for asset_id in record.asset_ids]
    return {"project_id": project_id, "assets": [asset for asset in assets if asset is not None]}
