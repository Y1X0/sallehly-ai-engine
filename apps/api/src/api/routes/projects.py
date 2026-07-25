from __future__ import annotations

from typing import Any, Callable

from auth import User
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from render_orchestrator import ProjectLifecycleError

from ..dependencies import get_app_state, get_current_user
from ..rate_limit import rate_limit_by_user
from ..state import AppState

router = APIRouter(prefix="/projects", tags=["projects"])

_generation_rate_limit_dep = Depends(rate_limit_by_user("generate_video", limit_attr="generation_rate_limit_per_minute"))


class CreateProjectRequest(BaseModel):
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


class FinalizeRequest(BaseModel):
    export_spec: dict[str, Any] | None = None


def _run(fn: Callable[..., Any], *args: Any) -> dict[str, Any]:
    try:
        record = fn(*args)
    except ProjectLifecycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return record.to_dict()


def _get_owned_project(project_id: str, state: AppState, current_user: User) -> dict[str, Any]:
    """Loads a project and enforces ownership. Every project-scoped route
    goes through this so a token can never read/mutate another user's
    project just by guessing an id."""
    record = state.project_store.get(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No such project: {project_id}")
    if record.created_by != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not the owner of this project")
    return record


@router.get("")
def list_projects(
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Lists projects in the caller's own workspace. `workspace_id` is
    never taken from the client - a token only ever sees its own
    personal workspace (see packages/auth's personal-workspace-per-user
    model)."""
    records = state.project_store.list_for_workspace(current_user.workspace_id)
    return {"projects": [record.to_dict() for record in records]}


@router.post("", status_code=201)
def create_project(
    body: CreateProjectRequest,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return _run(
        state.orchestrator.create_project,
        current_user.workspace_id,
        current_user.user_id,
        body.prompt,
        body.target_duration_sec,
        body.aspect_ratio,
        body.reference_asset_ids,
        body.style_preset_id,
    )


@router.get("/{project_id}")
def get_project(
    project_id: str,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return _get_owned_project(project_id, state, current_user).to_dict()


@router.post("/{project_id}/generate-plan")
def generate_plan(
    project_id: str,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _get_owned_project(project_id, state, current_user)
    return _run(state.orchestrator.generate_creative_plan, project_id)


@router.post("/{project_id}/approve-storyboard")
def approve_storyboard(
    project_id: str,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _get_owned_project(project_id, state, current_user)
    return _run(state.orchestrator.approve_storyboard, project_id)


@router.post("/{project_id}/reject-storyboard")
def reject_storyboard(
    project_id: str,
    body: RejectStoryboardRequest,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _get_owned_project(project_id, state, current_user)
    return _run(state.orchestrator.reject_storyboard, project_id, body.feedback)


@router.post("/{project_id}/approve-render")
def approve_render(
    project_id: str,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _get_owned_project(project_id, state, current_user)
    return _run(state.orchestrator.approve_render_plan, project_id)


@router.post("/{project_id}/reject-render")
def reject_render(
    project_id: str,
    body: RejectRenderRequest,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _get_owned_project(project_id, state, current_user)
    return _run(state.orchestrator.reject_render_plan, project_id, body.feedback, body.quality_tier)


@router.post("/{project_id}/generate-video", dependencies=[_generation_rate_limit_dep])
def generate_video(
    project_id: str,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _get_owned_project(project_id, state, current_user)
    return _run(state.orchestrator.generate_video, project_id)


@router.post("/{project_id}/retry-generation", dependencies=[_generation_rate_limit_dep])
def retry_generation(
    project_id: str,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _get_owned_project(project_id, state, current_user)
    return _run(state.orchestrator.retry_generation, project_id)


@router.get("/{project_id}/plan")
def get_plan(
    project_id: str,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """The DirectorPlan (scenes/shots) for the Creative Workspace UI's
    story editor/scene timeline/shot cards. Prefers the CreativeCompiler's
    enriched copy (director_plan_enriched: camera/lighting/motion/style
    filled in per shot) once storyboard compilation has run, falling
    back to the CreativeDirector's original plan before that."""
    _get_owned_project(project_id, state, current_user)
    entry = state.memory.latest(project_id, "director_plan_enriched") or state.memory.latest(
        project_id, "director_plan"
    )
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No plan generated yet for project {project_id}")
    return entry.content


@router.get("/{project_id}/storyboard")
def get_storyboard(
    project_id: str,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _get_owned_project(project_id, state, current_user)
    entry = state.memory.latest(project_id, "storyboard")
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No storyboard generated yet for project {project_id}")
    return entry.content


@router.get("/{project_id}/render-plan")
def get_render_plan(
    project_id: str,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _get_owned_project(project_id, state, current_user)
    entry = state.memory.latest(project_id, "render_plan")
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No render plan generated yet for project {project_id}")
    return entry.content


@router.post("/{project_id}/finalize")
def finalize_project(
    project_id: str,
    body: FinalizeRequest,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Assembles every generated shot into one exported deliverable
    (Timeline Builder -> FfmpegCompositor -> Export Service -> Asset
    Packager, ADR 0012/0014). Requires the project to be COMPLETED
    (every shot generated) and `ffmpeg`/`ffprobe` on `PATH`."""
    _get_owned_project(project_id, state, current_user)
    return _run(state.orchestrator.finalize_project, project_id, body.export_spec)


@router.get("/{project_id}/render-manifest")
def get_render_manifest(
    project_id: str,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    record = _get_owned_project(project_id, state, current_user)
    if record.render_manifest is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} has not been finalized yet")
    return record.render_manifest


@router.get("/{project_id}/assets")
def list_assets(
    project_id: str,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    record = _get_owned_project(project_id, state, current_user)
    assets = [state.asset_manager.get(asset_id) for asset_id in record.asset_ids]
    return {"project_id": project_id, "assets": [asset for asset in assets if asset is not None]}
