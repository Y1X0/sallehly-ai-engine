from __future__ import annotations

from typing import Any

import schemas

from .camera_continuity import CameraContinuityEngine
from .character_consistency import CharacterConsistencyEngine
from .environment_consistency import EnvironmentConsistencyEngine
from .memory_graph import DirectorMemoryGraph
from .object_consistency import ObjectConsistencyEngine
from .prompt_intelligence import PromptIntelligenceEngine
from .prompt_intelligence import register_defaults as _register_prompt_translators
from .quality_analyzer import SceneQualityAnalyzer
from .quality_analyzer import register_defaults as _register_quality_metrics
from .reference_images import ReferenceImageEngine
from .repair import AutomaticRepairEngine
from .repair import register_defaults as _register_repair_strategies
from .scene_continuity import SceneContinuityEngine
from .style_lock import StyleLockEngine
from .temporal_memory import TemporalMemoryEngine

_SEVERITY_PENALTY = {"critical": 0.4, "warning": 0.15, "info": 0.05}

# Free-text -> motion_direction heuristic. MotionDirector's subject_motion
# is a plain-language sentence ("character walks left to right") - this is
# the one place the Coordinator infers a structured continuity signal from
# it, rather than requiring an upstream schema change. Deliberately
# conservative: returns None (no signal, no false positive) for anything
# that doesn't clearly match.
_MOTION_DIRECTION_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("left to right", "left_to_right"),
    ("right to left", "right_to_left"),
    ("toward camera", "toward_camera"),
    ("towards camera", "toward_camera"),
    ("away from camera", "away_from_camera"),
)


class CinematicIntelligenceCoordinatorError(Exception):
    """Raised when a caller asks for a shot/project this coordinator has
    no recorded analysis for."""


class CinematicIntelligenceCoordinator:
    """The single integration point wiring every Phase 7 engine into the
    real project pipeline. Where Phase 7 shipped 10 engines that were
    each correct and tested in isolation, this class is what actually
    calls them in the right order against real upstream data (a
    project's enriched DirectorPlan and its compiled RenderPlan) and
    keeps the results a caller (API, dashboard) can query afterward.

    Two honest limitations, both documented rather than worked around:

    1. `scene.characters`/`Shot.description` are the only character
       information DirectorPlan carries today - no face/hair/clothing/
       age/skin-tone brief exists upstream. `_ensure_character` builds a
       placeholder `CharacterAttributes` from the character's name alone.
       The consistency guarantee this still provides is real (the same
       character_id, and therefore the same placeholder description, is
       reused for every shot referencing that name) - only the
       *richness* of the identity description is limited by what
       upstream data exists. A richer per-character brief in
       CreativeBrief/DirectorPlan is the natural fix, out of scope here.
    2. DirectorPlan has no object references at all (no `scene.objects`
       field exists), so this coordinator never auto-establishes
       ObjectProfiles - ObjectConsistencyEngine is wired and reachable
       via the API, but a project's objects must be registered
       explicitly (same as Phase 7's own tests exercise it) until
       DirectorPlan grows a real object-reference field.

    See docs/adr/0014-pipeline-integration.md.
    """

    def __init__(self) -> None:
        _register_prompt_translators()
        _register_quality_metrics()
        _register_repair_strategies()

        self.characters = CharacterConsistencyEngine()
        self.objects = ObjectConsistencyEngine()
        self.environments = EnvironmentConsistencyEngine()
        self.scene_continuity = SceneContinuityEngine()
        self.camera_continuity = CameraContinuityEngine()
        self.style_lock = StyleLockEngine()
        self.references = ReferenceImageEngine()
        self.prompts = PromptIntelligenceEngine()
        self.memory = TemporalMemoryEngine()
        self.graph = DirectorMemoryGraph()
        self.quality = SceneQualityAnalyzer()
        self.repair = AutomaticRepairEngine()

        self._environment_ids_by_location: dict[tuple[str, str], str] = {}
        self._director_plans: dict[str, dict[str, Any]] = {}
        self._engine_id_by_project: dict[str, str] = {}
        self._continuity_reports: dict[str, list[dict[str, Any]]] = {}
        self._quality_reports: dict[str, dict[str, dict[str, Any]]] = {}
        self._prompt_packages: dict[str, dict[str, dict[str, Any]]] = {}
        self._shot_context: dict[str, dict[str, dict[str, Any]]] = {}
        self._repair_actions: dict[str, list[dict[str, Any]]] = {}

    # ------------------------------------------------------------------
    # Pipeline integration: called from ProjectLifecycle.approve_storyboard
    # (and its reject/regenerate path), between Render Specification
    # compilation and the render-plan approval gate.
    # ------------------------------------------------------------------

    def enrich_render_plan(self, director_plan: dict[str, Any], render_plan: dict[str, Any]) -> dict[str, Any]:
        """Runs every Phase 7 engine against `director_plan` (the
        CreativeCompiler-enriched copy, camera/motion/lighting/style
        already filled in) and patches `render_plan`'s RenderSpecs in
        place with CIL-built prompts. Returns the same `render_plan`
        dict, mutated - callers persist it exactly as they did before
        this existed."""
        project_id = director_plan["project_id"]
        self._director_plans[project_id] = director_plan
        self._engine_id_by_project[project_id] = render_plan.get("engine_id", "")

        style_lock = self._ensure_style_lock(project_id, director_plan.get("global_style"))
        specs_by_shot_id = {spec["shot_id"]: spec for spec in render_plan["render_specs"]}

        cumulative_time = 0.0
        for scene in director_plan["scenes"]:
            scene_id = scene["scene_id"]
            environment = self._ensure_environment(project_id, scene)
            character_profiles = [self._ensure_character(project_id, name) for name in scene.get("characters", [])]
            character_ids = [profile["character_id"] for profile in character_profiles]

            prev_shot_state: dict[str, Any] | None = None
            for shot in sorted(scene["shots"], key=lambda s: s["order"]):
                shot_id = shot["shot_id"]
                duration = shot["duration_sec"]
                camera = shot.get("camera") or {}
                motion_direction = _infer_motion_direction((shot.get("motion") or {}).get("subject_motion"))

                shot_state: dict[str, Any] = {
                    "shot_id": shot_id,
                    "character_ids": character_ids,
                    "environment_id": environment["environment_id"] if environment else None,
                    "motion_direction": motion_direction,
                    "timing_sec": cumulative_time,
                    "duration_sec": duration,
                    "camera": camera,
                }
                lighting = shot.get("lighting") or {}
                if environment and lighting.get("time_of_day"):
                    shot_state["time_of_day"] = lighting["time_of_day"]

                scene_violations: list[dict[str, Any]] = []
                camera_violations: list[dict[str, Any]] = []
                if prev_shot_state is not None:
                    scene_report = self.scene_continuity.check(
                        project_id,
                        scene_id,
                        prev_shot_state,
                        shot_state,
                        environment_engine=self.environments,
                        object_engine=self.objects,
                        character_engine=self.characters,
                    )
                    self._continuity_reports.setdefault(project_id, []).append(scene_report)
                    scene_violations = [v for v in scene_report["violations"] if v.get("shot_id") == shot_id]

                    camera_report = self.camera_continuity.check(
                        project_id,
                        {"shot_id": prev_shot_state["shot_id"], "camera": prev_shot_state["camera"], "duration_sec": prev_shot_state["duration_sec"]},
                        {"shot_id": shot_id, "camera": camera, "duration_sec": duration},
                    )
                    self._continuity_reports.setdefault(project_id, []).append(camera_report)
                    camera_violations = [v for v in camera_report["violations"] if v.get("shot_id") == shot_id]

                style_violations: list[dict[str, Any]] = []
                if style_lock and shot.get("style_override"):
                    style_violations = self.style_lock.check_drift(project_id, shot["style_override"])

                camera_notes = _camera_notes(camera)
                continuity_notes = _continuity_notes(scene_violations + camera_violations)

                package = self.prompts.build(
                    project_id,
                    shot_id,
                    shot["description"],
                    characters=character_profiles,
                    objects=[],
                    environment=environment,
                    style_lock=style_lock,
                    camera_notes=camera_notes,
                    continuity_notes=continuity_notes,
                )
                package = self._translate(project_id, package)
                self._prompt_packages.setdefault(project_id, {})[shot_id] = package
                self._shot_context.setdefault(project_id, {})[shot_id] = {
                    "characters": character_profiles,
                    "objects": [],
                    "environment": environment,
                    "style_lock": style_lock,
                    "camera": camera,
                    "style_override": shot.get("style_override"),
                    "camera_notes": camera_notes,
                    "continuity_notes": continuity_notes,
                }

                spec = specs_by_shot_id.get(shot_id)
                if spec is not None:
                    spec["positive_prompt"] = package.get("translated_prompt") or package["positive_prompt"]
                    spec["negative_prompt"] = package["negative_prompt"]

                quality_report = self.quality.analyze(
                    project_id,
                    shot_id,
                    scene_violations=scene_violations,
                    camera_violations=camera_violations,
                    style_violations=style_violations,
                    prompt_score=package.get("score"),
                )
                self._quality_reports.setdefault(project_id, {})[shot_id] = quality_report

                self.memory.record_shot(
                    project_id,
                    shot_id,
                    scene_id,
                    shot["description"],
                    character_ids=character_ids,
                    environment_id=environment["environment_id"] if environment else None,
                    camera=camera or None,
                    order=shot["order"],
                )
                self.graph.record_event(
                    project_id,
                    f"evt_{shot_id}",
                    shot["description"],
                    character_ids=character_ids,
                    location_id=environment["environment_id"] if environment else None,
                )

                prev_shot_state = shot_state
                cumulative_time += duration

        if style_lock:
            self.graph.record_style(
                project_id, style_lock["style_lock_id"], style_lock["base_style"].get("visual_style", "style")
            )

        return render_plan

    def _translate(self, project_id: str, package: dict[str, Any]) -> dict[str, Any]:
        engine_id = self._engine_id_by_project.get(project_id)
        if not engine_id:
            return package
        try:
            return self.prompts.translate(package, engine_id)
        except KeyError:
            # No IPromptTranslator registered for this engine_id - the
            # untranslated, engine-agnostic prompt is still correct, just
            # not engine-tuned. Never a hard failure.
            return package

    def _ensure_style_lock(self, project_id: str, global_style: dict[str, Any] | None) -> dict[str, Any] | None:
        if self.style_lock.exists(project_id):
            return self.style_lock.get(project_id)
        if not global_style:
            return None
        lock = self.style_lock.lock(project_id, global_style)
        self.memory.set_style_lock(project_id, lock["style_lock_id"])
        return lock

    def _ensure_environment(self, project_id: str, scene: dict[str, Any]) -> dict[str, Any] | None:
        location = scene.get("location")
        if not location:
            return None
        key = (project_id, location)
        environment_id = self._environment_ids_by_location.get(key)
        if environment_id is None:
            environment_id = f"env_{schemas.content_hash({'project_id': project_id, 'location': location})}"
            self._environment_ids_by_location[key] = environment_id
        if self.environments.exists(environment_id):
            return self.environments.get(environment_id)

        profile = self.environments.establish(
            project_id, location, environment_id=environment_id, first_established_scene_id=scene["scene_id"]
        )
        self.memory.register_environment(project_id, environment_id)
        self.graph.record_location(project_id, environment_id, location)
        return profile

    def _ensure_character(self, project_id: str, name: str) -> dict[str, Any]:
        character_id = f"char_{schemas.content_hash({'project_id': project_id, 'name': name})}"
        if self.characters.exists(character_id):
            return self.characters.get(character_id)

        identity = {
            "face_description": f"the character referred to as {name!r} in this project's creative plan",
            "age_range": "adult",
            "skin_tone": "unspecified",
        }
        profile = self.characters.establish(project_id, name, identity, character_id=character_id)
        self.memory.register_character(project_id, character_id)
        self.graph.record_character(project_id, character_id, name)
        return profile

    # ------------------------------------------------------------------
    # API-facing operations
    # ------------------------------------------------------------------

    def get_project_report(self, project_id: str) -> dict[str, Any]:
        """The aggregated, dashboard-ready view: one score per
        consistency dimension, a flat problem list, and repair
        suggestions - built live from whatever this coordinator has
        recorded for the project so far. Safe to call repeatedly; it
        never mutates state."""
        quality_reports = list(self._quality_reports.get(project_id, {}).values())
        continuity_reports = self._continuity_reports.get(project_id, [])
        scene_reports = [r for r in continuity_reports if r["scope"] == "scene"]
        camera_reports = [r for r in continuity_reports if r["scope"] == "camera"]
        object_profiles = self.objects.list_for_project(project_id)
        object_violations = [
            v for r in continuity_reports for v in r["violations"] if v["violation_type"] == "object_location_conflict"
        ]

        camera_score = _mean(r["scores"]["camera_consistency"] for r in quality_reports)
        if camera_score is None:
            camera_score = _fraction_passed(camera_reports)

        scores = {
            "character_consistency": _mean(r["scores"]["identity_consistency"] for r in quality_reports),
            "object_consistency": _penalty_score(object_violations) if object_profiles else None,
            "scene_continuity": _fraction_passed(scene_reports),
            "camera_consistency": camera_score,
            "style": _mean(r["scores"]["style_consistency"] for r in quality_reports),
        }
        present = [v for v in scores.values() if v is not None]
        scores["overall"] = round(sum(present) / len(present), 4) if present else None

        problems: list[dict[str, Any]] = []
        for report in continuity_reports:
            problems.extend({**v, "source": "continuity"} for v in report["violations"])
        for report in quality_reports:
            problems.extend({**issue, "source": "quality", "shot_id": report["shot_id"]} for issue in report["issues"])

        repair_suggestions = [
            {
                "shot_id": r["shot_id"],
                "report_id": r["report_id"],
                "overall_score": r["scores"]["overall"],
                "worst_dimension": min((k for k in r["scores"] if k != "overall"), key=lambda k: r["scores"][k]),
            }
            for r in quality_reports
            if r["repair_recommended"]
        ]

        return {
            "project_id": project_id,
            "scores": scores,
            "problems": problems,
            "repair_suggestions": repair_suggestions,
            "character_count": len(self.characters.list_for_project(project_id)),
            "object_count": len(object_profiles),
            "environment_count": len(self.environments.list_for_project(project_id)),
            "shots_analyzed": len(quality_reports),
        }

    def improve_prompt(self, project_id: str, shot_id: str) -> dict[str, Any]:
        """Rebuilds a shot's PromptPackage from the same resolved
        character/object/environment/style context `enrich_render_plan`
        used, bumping its version (PromptVersioning). Does not touch any
        already-approved RenderPlan - a caller decides whether to push
        the improved prompt into a regenerated render plan."""
        context = self._shot_context.get(project_id, {}).get(shot_id)
        if context is None:
            raise CinematicIntelligenceCoordinatorError(
                f"No recorded context for shot {shot_id!r} in project {project_id!r} - "
                "run the render-plan enrichment (approve the storyboard) first"
            )
        description = self._shot_description(project_id, shot_id) or ""
        package = self.prompts.build(
            project_id,
            shot_id,
            description,
            characters=context.get("characters"),
            objects=context.get("objects"),
            environment=context.get("environment"),
            style_lock=context.get("style_lock"),
            camera_notes=context.get("camera_notes"),
            continuity_notes=context.get("continuity_notes"),
        )
        package = self._translate(project_id, package)
        self._prompt_packages.setdefault(project_id, {})[shot_id] = package
        return package

    def repair_shot(self, project_id: str, shot_id: str) -> dict[str, Any]:
        """Runs the Automatic Repair Engine against a shot's most recent
        QualityReport, always scoped to that one shot."""
        quality_report = self._quality_reports.get(project_id, {}).get(shot_id)
        if quality_report is None:
            raise CinematicIntelligenceCoordinatorError(
                f"No QualityReport for shot {shot_id!r} in project {project_id!r} - analyze it first"
            )
        context = self._build_repair_context(project_id, shot_id)
        action = self.repair.repair(quality_report, context=context)
        action = {**action, "review_status": "pending"}
        self._repair_actions.setdefault(project_id, []).append(action)
        return action

    def review_repair(self, project_id: str, repair_id: str, approved: bool) -> dict[str, Any]:
        """Records a human decision on a previously proposed RepairAction
        - "approve/reject cinematic suggestions". Marking review_status
        is a record of the decision; actually applying an approved
        repair (e.g. rebuilding a shot's RenderSpec and re-queuing
        generation) is a caller-level action, not performed here."""
        actions = self._repair_actions.get(project_id, [])
        for index, action in enumerate(actions):
            if action["repair_id"] == repair_id:
                actions[index] = {**action, "review_status": "approved" if approved else "rejected"}
                return actions[index]
        raise CinematicIntelligenceCoordinatorError(f"No RepairAction {repair_id!r} for project {project_id!r}")

    def list_repairs(self, project_id: str) -> list[dict[str, Any]]:
        return list(self._repair_actions.get(project_id, []))

    def _build_repair_context(self, project_id: str, shot_id: str) -> dict[str, Any]:
        shot_context = self._shot_context.get(project_id, {}).get(shot_id, {})
        prompt_package = self._prompt_packages.get(project_id, {}).get(shot_id)
        project_memory = self.memory.get_or_create(project_id)
        style_lock = self.style_lock.get(project_id) if self.style_lock.exists(project_id) else None

        characters = shot_context.get("characters") or []
        last_camera_state = project_memory.get("last_camera_state")
        last_known_good_camera = None
        if last_camera_state and last_camera_state.get("shot_id") != shot_id:
            last_known_good_camera = last_camera_state.get("camera")

        return {
            "current_positive_prompt": prompt_package["positive_prompt"] if prompt_package else None,
            "current_camera": shot_context.get("camera"),
            "last_known_good_camera": last_known_good_camera,
            "style_lock_base_style": style_lock["base_style"] if style_lock else None,
            "current_style_override": shot_context.get("style_override"),
            "character_profile": characters[0] if characters else None,
            "environment_profile": shot_context.get("environment"),
        }

    def _shot_description(self, project_id: str, shot_id: str) -> str | None:
        director_plan = self._director_plans.get(project_id, {})
        for scene in director_plan.get("scenes", []):
            for shot in scene["shots"]:
                if shot["shot_id"] == shot_id:
                    return shot["description"]
        return None


def _infer_motion_direction(subject_motion: str | None) -> str | None:
    if not subject_motion:
        return None
    lowered = subject_motion.lower()
    for keyword, direction in _MOTION_DIRECTION_KEYWORDS:
        if keyword in lowered:
            return direction
    return None


def _camera_notes(camera: dict[str, Any]) -> str | None:
    if not camera:
        return None
    bits = []
    if camera.get("shot_type"):
        bits.append(str(camera["shot_type"]).replace("_", " "))
    movement_type = (camera.get("movement") or {}).get("type")
    if movement_type:
        bits.append(str(movement_type).replace("_", " "))
    return ", ".join(bits) if bits else None


def _continuity_notes(violations: list[dict[str, Any]]) -> str | None:
    if not violations:
        return None
    return "; ".join(v["description"] for v in violations[:3])


def _mean(values: Any) -> float | None:
    values = list(values)
    return round(sum(values) / len(values), 4) if values else None


def _fraction_passed(reports: list[dict[str, Any]]) -> float | None:
    if not reports:
        return None
    return round(sum(1 for r in reports if r["passed"]) / len(reports), 4)


def _penalty_score(violations: list[dict[str, Any]]) -> float:
    score = 1.0
    for violation in violations:
        score -= _SEVERITY_PENALTY.get(violation.get("severity"), 0.1)
    return round(max(0.0, min(1.0, score)), 4)
