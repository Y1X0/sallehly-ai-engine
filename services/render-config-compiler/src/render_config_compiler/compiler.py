from __future__ import annotations

import math
from typing import Any

import schemas
from video_engine_sdk import CapabilityManifest


class RenderConfigCompiler:
    """Converts a fully-planned DirectorPlan (every shot's camera/motion/
    lighting populated) into engine-agnostic RenderSpecs - one per shot,
    or several if a shot's duration exceeds the active engine's
    max_shot_duration_sec.

    Takes a CapabilityManifest as a plain parameter rather than importing
    any specific engine adapter - this is what keeps it usable for Wan2.1,
    a future custom foundation model, or a test double manifest, all
    without touching this class. See docs/adr/0002-compute-provider-abstraction.md
    and docs/adr/0001-director-engine-separation.md.
    """

    def compile(
        self,
        director_plan: dict[str, Any],
        capability_manifest: CapabilityManifest,
        quality_tier: str = "final",
    ) -> list[dict[str, Any]]:
        global_style = director_plan["global_style"]
        negative_prompt = director_plan.get("negative_prompt_global", "")
        resolution = self._select_resolution(director_plan["aspect_ratio"], capability_manifest)
        fps = capability_manifest.fps_options[0]

        render_specs: list[dict[str, Any]] = []
        global_index = 0
        for scene in director_plan["scenes"]:
            for shot in scene["shots"]:
                render_specs.extend(
                    self._compile_shot(
                        shot,
                        director_plan["aspect_ratio"],
                        global_style,
                        negative_prompt,
                        resolution,
                        fps,
                        capability_manifest,
                        quality_tier,
                        global_index,
                    )
                )
                global_index += 1

        for spec in render_specs:
            schemas.validate(spec, "render_configuration")
        return render_specs

    def _compile_shot(
        self,
        shot: dict[str, Any],
        aspect_ratio: str,
        global_style: dict[str, Any],
        negative_prompt: str,
        resolution: str,
        fps: int,
        manifest: CapabilityManifest,
        quality_tier: str,
        global_index: int,
    ) -> list[dict[str, Any]]:
        sub_shots = self._split_for_duration(shot, manifest.max_shot_duration_sec)
        mode = self._select_mode(shot, manifest)

        specs = []
        for sub_shot_id, duration in sub_shots:
            spec: dict[str, Any] = {
                "schema_version": "1.0",
                "shot_id": sub_shot_id,
                "duration_sec": duration,
                "fps": fps,
                "resolution": resolution,
                "aspect_ratio": aspect_ratio,
                "mode": mode,
                "positive_prompt": self._compose_prompt(shot, global_style),
                "negative_prompt": negative_prompt,
                "camera": shot["camera"],
                "lighting": shot["lighting"],
                "engine_id": manifest.engine_id,
                "quality_tier": quality_tier,
            }

            if manifest.supports_seed and "consistency_seed" in global_style:
                spec["seed"] = global_style["consistency_seed"] + global_index

            if "motion" in shot:
                spec["motion_strength"] = self._rescale_motion(
                    shot["motion"]["motion_strength"], manifest.motion_strength_range
                )

            if (
                mode == "image_to_video"
                and manifest.supports_conditioning_images
                and shot.get("asset_references")
            ):
                spec["conditioning_images"] = shot["asset_references"][: manifest.max_conditioning_images]

            specs.append(spec)
        return specs

    @staticmethod
    def _select_mode(shot: dict[str, Any], manifest: CapabilityManifest) -> str:
        if shot.get("asset_references") and "image_to_video" in manifest.modes:
            return "image_to_video"
        return "text_to_video"

    @staticmethod
    def _split_for_duration(shot: dict[str, Any], max_duration_sec: float) -> list[tuple[str, float]]:
        duration = shot["duration_sec"]
        if duration <= max_duration_sec:
            return [(shot["shot_id"], duration)]

        num_parts = math.ceil(duration / max_duration_sec)
        part_duration = round(duration / num_parts, 2)
        return [(f"{shot['shot_id']}_part{i + 1}", part_duration) for i in range(num_parts)]

    @staticmethod
    def _select_resolution(aspect_ratio: str, manifest: CapabilityManifest) -> str:
        target_ratio = RenderConfigCompiler._ratio(aspect_ratio, separator=":")

        def ratio_diff(resolution: str) -> float:
            return abs(RenderConfigCompiler._ratio(resolution, separator="x") - target_ratio)

        return min(manifest.resolutions, key=ratio_diff)

    @staticmethod
    def _ratio(value: str, separator: str) -> float:
        width, height = (int(part) for part in value.split(separator))
        return width / height

    @staticmethod
    def _rescale_motion(value: float, target_range: tuple[float, float]) -> float:
        low, high = target_range
        return round(low + (value / 100.0) * (high - low), 2)

    @staticmethod
    def _compose_prompt(shot: dict[str, Any], global_style: dict[str, Any]) -> str:
        camera = shot["camera"]
        lighting = shot["lighting"]
        parts = [
            shot["description"],
            f"{camera['shot_type'].replace('_', ' ')} shot",
            f"{camera['focal_length_mm_equiv']}mm lens",
            f"{camera['movement']['type'].replace('_', ' ')} camera movement",
            f"{lighting['time_of_day'].replace('_', ' ')} lighting",
            lighting["mood"],
            global_style.get("visual_style", ""),
        ]
        return ", ".join(part for part in parts if part)
