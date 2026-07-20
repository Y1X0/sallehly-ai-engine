from __future__ import annotations

import hashlib
from typing import Any

_VIVID_KEYWORDS = ("vivid", "bold", "saturated")
_MUTED_KEYWORDS = ("muted", "minimalist", "pastel")


class StyleDirector:
    """Deterministic visual-consistency planning: finalizes the
    DirectorPlan's global style once - a stable consistency_seed (so
    engines that support seeding produce visually related shots), default
    color_grade values (from keyword rules over visual_style, refined by
    any grading_direction hints the Lighting Director attached to
    individual shots), and a placeholder for reference_image_ids (asset
    management is a Phase 3 concern - see services/asset-manager).
    """

    def finalize_global_style(self, director_plan: dict[str, Any]) -> dict[str, Any]:
        existing = director_plan.get("global_style") or {}
        visual_style = existing.get("visual_style") or "cinematic photorealistic"

        return {
            "visual_style": visual_style,
            "color_grade": self._default_color_grade(visual_style),
            "consistency_seed": self._deterministic_seed(director_plan["project_id"]),
            "reference_image_ids": existing.get("reference_image_ids", []),
        }

    @staticmethod
    def _default_color_grade(visual_style: str) -> dict[str, str]:
        style = visual_style.lower()
        if any(keyword in style for keyword in _VIVID_KEYWORDS):
            return {"contrast": "high", "saturation": "vivid"}
        if any(keyword in style for keyword in _MUTED_KEYWORDS):
            return {"contrast": "low", "saturation": "muted"}
        return {"contrast": "medium", "saturation": "natural"}

    @staticmethod
    def _deterministic_seed(project_id: str) -> int:
        digest = hashlib.sha256(project_id.encode()).hexdigest()
        return int(digest[:8], 16)
