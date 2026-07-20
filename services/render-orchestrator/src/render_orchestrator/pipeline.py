from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from asset_manager import AssetManager
from video_engine_sdk import ComputeJobStatus, IComputeProvider, IVideoEngine
from video_engine_sdk import RenderSpec as EngineRenderSpec

from .jobs import GenerationJob, GenerationJobStatus, IGenerationJobStore, InMemoryGenerationJobStore


class GenerationPipelineError(Exception):
    """Raised internally when a compute job doesn't reach SUCCEEDED -
    caught by GenerationPipeline itself and turned into a FAILED
    GenerationJob with error_message set; not expected to escape
    generate_shot()."""


class GenerationPipeline:
    """Bridges CreativeCompiler's engine-agnostic RenderSpec dicts
    (render_configuration.schema.json) to a concrete IVideoEngine +
    IComputeProvider pair, tracking each shot as a GenerationJob.

        RenderSpec dict -> IVideoEngine.build_job_payload
                         -> IComputeProvider.submit/poll/fetch_output
                         -> IVideoEngine.parse_result -> RawClip
                         -> AssetManager.register_video

    Neither CreativeDirector nor CreativeCompiler import this class or
    anything from services/video-engine-adapter - this is the one place
    those two abstract interfaces get bound to concrete implementations,
    selected entirely by what's injected into __init__ (see
    docs/adr/0001-director-engine-separation.md, ADR 0002, ADR 0009).
    """

    def __init__(
        self,
        engine: IVideoEngine,
        compute_provider: IComputeProvider,
        asset_manager: AssetManager | None = None,
        job_store: IGenerationJobStore | None = None,
        max_retries: int = 2,
        poll_interval_sec: float = 0.0,
        poll_timeout_sec: float = 300.0,
    ) -> None:
        self._engine = engine
        self._compute = compute_provider
        self._assets = asset_manager or AssetManager()
        self._jobs = job_store or InMemoryGenerationJobStore()
        self._max_retries = max_retries
        self._poll_interval_sec = poll_interval_sec
        self._poll_timeout_sec = poll_timeout_sec

    def generate_shot(self, project_id: str, render_spec_dict: dict[str, Any]) -> GenerationJob:
        job = GenerationJob(
            job_id=f"job_{uuid.uuid4().hex[:12]}",
            project_id=project_id,
            shot_id=render_spec_dict["shot_id"],
            render_spec=render_spec_dict,
            engine_id=self._engine.capabilities().engine_id,
            compute_provider_id=self._compute.provider_id,
        )
        self._save(job)

        # retry_count ends up meaning "how many retries this job needed":
        # 0 if it succeeded on the first attempt, N if it took N retries
        # (whether it ultimately succeeded or exhausted max_retries failing).
        for attempt in range(self._max_retries + 1):
            try:
                self._run_once(job, render_spec_dict)
                job.retry_count = attempt
                self._save(job)
                return job
            except Exception as exc:  # noqa: BLE001 - any failure here means the job failed, by design
                job.retry_count = attempt
                job.error_message = str(exc)
                job.status = GenerationJobStatus.FAILED
                self._save(job)
        return job

    def generate_plan(self, render_plan: dict[str, Any]) -> list[GenerationJob]:
        """Convenience for running every RenderSpec in an approved
        RenderPlan (render_plan.schema.json)."""
        return [
            self.generate_shot(render_plan["project_id"], spec)
            for spec in render_plan["render_specs"]
        ]

    def _run_once(self, job: GenerationJob, render_spec_dict: dict[str, Any]) -> None:
        job.status = GenerationJobStatus.RUNNING
        self._save(job)

        spec = _render_spec_from_dict(render_spec_dict)
        payload = self._engine.build_job_payload(spec)
        handle = self._compute.submit(payload)
        job.external_job_id = handle.external_job_id
        self._save(job)

        status = self._await_completion(handle)
        if status != ComputeJobStatus.SUCCEEDED:
            raise GenerationPipelineError(f"Compute job ended with status={status.value}")

        output = self._compute.fetch_output(handle)
        raw_clip = self._engine.parse_result(spec, output)
        asset = self._assets.register_video(project_id=job.project_id, shot_id=job.shot_id, raw_clip=raw_clip)

        job.output_asset_id = asset["asset_id"]
        job.status = GenerationJobStatus.COMPLETED
        self._save(job)

    def _await_completion(self, handle: Any) -> ComputeJobStatus:
        deadline = time.monotonic() + self._poll_timeout_sec
        while True:
            status = self._compute.get_status(handle)
            if status in (ComputeJobStatus.SUCCEEDED, ComputeJobStatus.FAILED, ComputeJobStatus.CANCELLED):
                return status
            if time.monotonic() > deadline:
                raise GenerationPipelineError("Polling timed out waiting for the compute job to finish")
            if self._poll_interval_sec:
                time.sleep(self._poll_interval_sec)

    def _save(self, job: GenerationJob) -> None:
        job.updated_at = datetime.now(timezone.utc).isoformat()
        self._jobs.save(job)


def _render_spec_from_dict(render_spec: dict[str, Any]) -> EngineRenderSpec:
    """Converts a schema-validated RenderSpec dict (the wire format
    CreativeCompiler produces) into the video_engine_sdk.types.RenderSpec
    dataclass IVideoEngine implementations expect. See
    docs/adr/0009-generation-pipeline.md for why this conversion exists
    here rather than CreativeCompiler producing dataclasses directly."""
    return EngineRenderSpec(
        schema_version=render_spec["schema_version"],
        shot_id=render_spec["shot_id"],
        duration_sec=render_spec["duration_sec"],
        fps=render_spec["fps"],
        resolution=render_spec["resolution"],
        positive_prompt=render_spec["positive_prompt"],
        aspect_ratio=render_spec.get("aspect_ratio"),
        mode=render_spec.get("mode", "text_to_video"),
        negative_prompt=render_spec.get("negative_prompt"),
        seed=render_spec.get("seed"),
        motion_strength=render_spec.get("motion_strength"),
        camera=render_spec.get("camera"),
        lighting=render_spec.get("lighting"),
        conditioning_images=render_spec.get("conditioning_images", []),
        engine_id=render_spec.get("engine_id"),
        quality_tier=render_spec.get("quality_tier", "final"),
    )
