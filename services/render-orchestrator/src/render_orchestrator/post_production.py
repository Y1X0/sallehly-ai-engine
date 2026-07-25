from __future__ import annotations

from pathlib import Path
from typing import Any

from asset_manager import AssetManager
from export_service import AssetPackager, ExportService
from post_processing import TimelineBuilder
from post_processing import register_defaults as register_transition_defaults
from post_processing.compositor import FfmpegCompositor, timeline_from_dict


class PostProductionRunnerError(Exception):
    """Raised when a project has no generated video assets to compose."""


class PostProductionRunner:
    """Bridges GenerationPipeline's completed per-shot clips to a final,
    exported deliverable: TimelineBuilder -> FfmpegCompositor ->
    ExportService -> AssetPackager (services/post-processing,
    services/export-service - ADR 0012). This is the "Post Processing ->
    Export" tail of the pipeline; `ProjectLifecycle.finalize_project`
    calls it once every shot in a project has GENERATED successfully.

    Optional by design: a `ProjectLifecycle` built without a
    `PostProductionRunner` behaves exactly as it did before this existed
    (COMPLETED is still the terminal state after generation) - see
    docs/adr/0014-pipeline-integration.md. Requires `ffmpeg`/`ffprobe` on
    `PATH` (ADR 0012); raises `post_processing.FfmpegNotAvailableError`
    with a clear message if it isn't.
    """

    def __init__(self, asset_manager: AssetManager, output_root: str | Path = "./.docker-data/renders") -> None:
        register_transition_defaults()
        self._assets = asset_manager
        self._timeline_builder = TimelineBuilder()
        self._compositor = FfmpegCompositor(asset_manager=asset_manager)
        self._export = ExportService(asset_manager)
        self._packager = AssetPackager()
        self._output_root = Path(output_root)

    def finalize(
        self,
        director_plan: dict[str, Any],
        render_plan: dict[str, Any] | None = None,
        export_spec: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Returns a schema-valid RenderManifest (render_manifest.schema.json)."""
        project_id = director_plan["project_id"]
        video_assets_by_shot_id = {
            record["shot_id"]: record
            for record in self._assets.list_for_project(project_id, kind="video")
            if record.get("shot_id")
        }
        if not video_assets_by_shot_id:
            raise PostProductionRunnerError(f"No generated video assets for project {project_id}")

        timeline_dict = self._timeline_builder.build(director_plan, video_assets_by_shot_id, render_plan)
        output_path = self._output_root / project_id / "master.mp4"
        composition = self._compositor.compose(timeline_from_dict(timeline_dict), output_path)
        self._assets.register(
            project_id, kind="video", uri=composition.output_uri, metadata={"role": "post_production_master"}
        )

        export_result = self._export.export(
            project_id, composition.output_uri, export_spec or {"format": "mp4", "quality_preset": "1080p"}
        )
        return self._packager.package(project_id, export_result)
