from __future__ import annotations

from typing import Any

from auth import User
from cinematic_intelligence import CinematicIntelligenceCoordinatorError
from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_app_state, get_current_user
from ..state import AppState

router = APIRouter(prefix="/projects/{project_id}/cinematic", tags=["cinematic-intelligence"])


def _get_owned_project(project_id: str, state: AppState, current_user: User) -> None:
    """Same ownership check as routes/projects.py - every project-scoped
    route goes through this so a token can never read/mutate another
    user's project just by guessing an id."""
    record = state.project_store.get(project_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No such project: {project_id}")
    if record.created_by != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not the owner of this project")


@router.post("/analyze")
def analyze_project(
    project_id: str,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Character/object/scene/camera/style consistency scores, detected
    problems, and repair suggestions - computed live from whatever the
    Cinematic Intelligence Layer has recorded for this project so far
    (populated automatically when the storyboard is approved - see
    ProjectLifecycle._enrich_render_plan, ADR 0014)."""
    _get_owned_project(project_id, state, current_user)
    return state.cinematic_intelligence.get_project_report(project_id)


@router.get("/report")
def get_report(
    project_id: str,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Read-only alias for POST .../analyze - both return the same live
    aggregation, neither mutates state."""
    _get_owned_project(project_id, state, current_user)
    return state.cinematic_intelligence.get_project_report(project_id)


@router.post("/prompts/{shot_id}/improve")
def improve_prompt(
    project_id: str,
    shot_id: str,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Rebuilds one shot's PromptPackage from its resolved character/
    object/environment/style context, bumping its version."""
    _get_owned_project(project_id, state, current_user)
    try:
        return state.cinematic_intelligence.improve_prompt(project_id, shot_id)
    except CinematicIntelligenceCoordinatorError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/repair/{shot_id}")
def repair_shot(
    project_id: str,
    shot_id: str,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Runs the Automatic Repair Engine against a shot's most recent
    QualityReport - always scoped to that one shot, never the whole
    project. The returned RepairAction starts `review_status="pending"`;
    a human accepts/rejects it via the endpoints below."""
    _get_owned_project(project_id, state, current_user)
    try:
        return state.cinematic_intelligence.repair_shot(project_id, shot_id)
    except CinematicIntelligenceCoordinatorError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/repairs")
def list_repairs(
    project_id: str,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _get_owned_project(project_id, state, current_user)
    return {"repairs": state.cinematic_intelligence.list_repairs(project_id)}


@router.post("/repairs/{repair_id}/approve")
def approve_repair(
    project_id: str,
    repair_id: str,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _get_owned_project(project_id, state, current_user)
    try:
        return state.cinematic_intelligence.review_repair(project_id, repair_id, approved=True)
    except CinematicIntelligenceCoordinatorError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/repairs/{repair_id}/reject")
def reject_repair(
    project_id: str,
    repair_id: str,
    state: AppState = Depends(get_app_state),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _get_owned_project(project_id, state, current_user)
    try:
        return state.cinematic_intelligence.review_repair(project_id, repair_id, approved=False)
    except CinematicIntelligenceCoordinatorError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
