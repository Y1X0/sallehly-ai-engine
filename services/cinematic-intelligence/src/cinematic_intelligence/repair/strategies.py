from __future__ import annotations

from typing import Any

from cinematic_intelligence_sdk import IRepairStrategy, QualityReport, RepairAction

from .._util import new_id, now_iso
from ..prompt_intelligence.optimizer import NegativePromptBuilder

_STYLE_FIELDS_TO_REASSERT = ("visual_style", "color_grade")


class PromptRepairStrategy(IRepairStrategy):
    """Repairs a shot whose worst-scoring dimension is composition or
    prompt adherence: reinforces the positive prompt with an explicit
    consistency directive and strengthens the negative prompt against
    the specific failure mode. Expects `context` to carry
    `current_positive_prompt` and `current_version`."""

    repair_type = "prompt_repair"

    def repair(self, quality_report: QualityReport, context: dict[str, Any]) -> RepairAction:
        current_prompt = context.get("current_positive_prompt")
        if not current_prompt:
            return _failed(quality_report, self.repair_type, "no current_positive_prompt supplied")

        reinforced = f"{current_prompt}, maintaining consistent established appearance and continuity"
        negative = NegativePromptBuilder().build(
            extra_terms=["identity drift", "inconsistent appearance between frames"]
        )
        return RepairAction(
            schema_version="1.0",
            repair_id=new_id("repair"),
            project_id=quality_report.project_id,
            shot_id=quality_report.shot_id,
            quality_report_id=quality_report.report_id,
            repair_type=self.repair_type,
            strategy_id=self.repair_type,
            status="applied",
            description="Reinforced positive prompt and strengthened negative prompt",
            before_summary=current_prompt,
            after_summary=f"positive={reinforced} | negative={negative}",
            applied_at=now_iso(),
        )


class CameraRepairStrategy(IRepairStrategy):
    """Repairs a shot whose camera/motion consistency dropped by
    reverting to the last known-good camera setup. Expects `context` to
    carry `current_camera` and, if available, `last_known_good_camera`
    (typically ProjectMemory.last_camera_state.camera)."""

    repair_type = "camera_repair"

    def repair(self, quality_report: QualityReport, context: dict[str, Any]) -> RepairAction:
        last_known_good = context.get("last_known_good_camera")
        if not last_known_good:
            return _failed(quality_report, self.repair_type, "no last_known_good_camera available to revert to")

        return RepairAction(
            schema_version="1.0",
            repair_id=new_id("repair"),
            project_id=quality_report.project_id,
            shot_id=quality_report.shot_id,
            quality_report_id=quality_report.report_id,
            repair_type=self.repair_type,
            strategy_id=self.repair_type,
            status="applied",
            description="Reverted camera setup to the last known-good state",
            before_summary=str(context.get("current_camera")),
            after_summary=str(last_known_good),
            applied_at=now_iso(),
        )


class StyleRepairStrategy(IRepairStrategy):
    """Repairs a shot that drifted from the project's StyleLock by
    reasserting the locked visual_style/color_grade onto the shot's
    style_override. Expects `context` to carry `style_lock_base_style`
    and `current_style_override`."""

    repair_type = "style_repair"

    def repair(self, quality_report: QualityReport, context: dict[str, Any]) -> RepairAction:
        base_style = context.get("style_lock_base_style")
        if not base_style:
            return _failed(quality_report, self.repair_type, "no style_lock_base_style available to reassert")

        current_override = context.get("current_style_override") or {}
        repaired_override = dict(current_override)
        for field_name in _STYLE_FIELDS_TO_REASSERT:
            if field_name in base_style:
                repaired_override[field_name] = base_style[field_name]

        return RepairAction(
            schema_version="1.0",
            repair_id=new_id("repair"),
            project_id=quality_report.project_id,
            shot_id=quality_report.shot_id,
            quality_report_id=quality_report.report_id,
            repair_type=self.repair_type,
            strategy_id=self.repair_type,
            status="applied",
            description="Reasserted locked style fields onto the shot's style_override",
            before_summary=str(current_override),
            after_summary=str(repaired_override),
            applied_at=now_iso(),
        )


class IdentityRepairStrategy(IRepairStrategy):
    """Repairs a shot with identity drift by re-attaching the character's
    CharacterIdentityProfile reference images and consistency seed.
    Expects `context` to carry `character_profile` (a
    CharacterIdentityProfile dict)."""

    repair_type = "identity_repair"

    def repair(self, quality_report: QualityReport, context: dict[str, Any]) -> RepairAction:
        profile = context.get("character_profile")
        if not profile:
            return _failed(quality_report, self.repair_type, "no character_profile available to reattach")

        after = (
            f"reference_image_ids={profile.get('reference_image_ids', [])}, "
            f"consistency_seed={profile.get('consistency_seed')}"
        )
        return RepairAction(
            schema_version="1.0",
            repair_id=new_id("repair"),
            project_id=quality_report.project_id,
            shot_id=quality_report.shot_id,
            quality_report_id=quality_report.report_id,
            repair_type=self.repair_type,
            strategy_id=self.repair_type,
            status="applied",
            description="Reattached the established CharacterIdentityProfile's references",
            before_summary="prompt did not reference the locked identity profile",
            after_summary=after,
            applied_at=now_iso(),
        )


class LightingRepairStrategy(IRepairStrategy):
    """Repairs a shot with lighting/environment discontinuity by
    realigning it to the shot's EnvironmentProfile. Expects `context` to
    carry `environment_profile`."""

    repair_type = "lighting_repair"

    def repair(self, quality_report: QualityReport, context: dict[str, Any]) -> RepairAction:
        environment = context.get("environment_profile")
        if not environment:
            return _failed(quality_report, self.repair_type, "no environment_profile available to align to")

        after = f"time_of_day={environment.get('time_of_day')}, weather={environment.get('weather')}"
        return RepairAction(
            schema_version="1.0",
            repair_id=new_id("repair"),
            project_id=quality_report.project_id,
            shot_id=quality_report.shot_id,
            quality_report_id=quality_report.report_id,
            repair_type=self.repair_type,
            strategy_id=self.repair_type,
            status="applied",
            description="Realigned shot lighting to the established EnvironmentProfile",
            before_summary="shot lighting diverged from the established environment",
            after_summary=after,
            applied_at=now_iso(),
        )


def _failed(quality_report: QualityReport, repair_type: str, reason: str) -> RepairAction:
    return RepairAction(
        schema_version="1.0",
        repair_id=new_id("repair"),
        project_id=quality_report.project_id,
        shot_id=quality_report.shot_id,
        quality_report_id=quality_report.report_id,
        repair_type=repair_type,
        strategy_id=repair_type,
        status="failed",
        description=reason,
        applied_at=now_iso(),
    )
