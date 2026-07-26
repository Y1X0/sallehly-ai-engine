from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from video_engine_sdk import (
    ComputeJobHandle,
    ComputeJobStatus,
    EngineJobOutput,
    EngineJobPayload,
    IComputeProvider,
)

from ..inference import generate_video

PROVIDER_ID = "local-inference"


class LocalInferenceProvider(IComputeProvider):
    """Real (never mocked), no-external-credentials `IComputeProvider`:
    runs `video_engine_adapter.inference.generate_video` synchronously
    inside `submit()` and writes a real `.mp4` file - unlike
    `LocalProvider`, which only ever writes a JSON stub and never
    actually generates anything.

    Default (`smoke_test=True`) uses a tiny-but-real WanPipeline (see
    `inference.wan_inference`'s docstring) so this runs anywhere with no
    GPU, no API key, and no rented compute - the same zero-setup posture
    `LocalProvider` has, but producing a genuinely computed video
    instead of a stub. Set `smoke_test=False` with a real `model_id` to
    run real full-scale Wan2.1/2.2 inference locally instead (requires a
    real CUDA GPU and real downloaded weights - see
    `inference.wan_inference.build_real_pipeline`).

    `submit()` deliberately lets `generate_video`'s exceptions propagate
    rather than catching them into a "failed" file marker:
    `render_orchestrator.GenerationPipeline.generate_shot()` already
    wraps every `compute_provider` call in a try/except that records
    `error_message` and marks the job FAILED (see pipeline.py) - the
    same mechanism `RunPodProvider` relies on for its own errors. This
    is what turns "no CUDA GPU for a real request" or "missing
    model_id" into a clear, user-visible reason instead of a silent
    mock success.
    """

    provider_id = PROVIDER_ID

    def __init__(
        self,
        output_dir: str = "./.docker-data/local-inference-output",
        *,
        smoke_test: bool = True,
        model_id: str | None = None,
        device: str = "cpu",
        seed: int = 0,
    ) -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._smoke_test = smoke_test
        self._model_id = model_id
        self._device = device
        self._seed = seed

    def submit(self, payload: EngineJobPayload) -> ComputeJobHandle:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        job_id = str(uuid.uuid4())
        video_path = self._output_dir / f"{job_id}.mp4"
        metadata_path = self._output_dir / f"{job_id}.json"

        result = generate_video(
            payload.input, output_path=video_path,
            smoke_test=self._smoke_test, model_id=self._model_id, device=self._device, seed=self._seed,
        )
        metadata_path.write_text(json.dumps({"provider": self.provider_id, **result}, indent=2))
        return ComputeJobHandle(provider_id=self.provider_id, external_job_id=job_id)

    def get_status(self, handle: ComputeJobHandle) -> ComputeJobStatus:
        video_path = self._output_dir / f"{handle.external_job_id}.mp4"
        return ComputeJobStatus.SUCCEEDED if video_path.exists() else ComputeJobStatus.FAILED

    def fetch_output(self, handle: ComputeJobHandle) -> EngineJobOutput:
        video_path = self._output_dir / f"{handle.external_job_id}.mp4"
        metadata_path = self._output_dir / f"{handle.external_job_id}.json"
        metadata: dict[str, Any] = json.loads(metadata_path.read_text()) if metadata_path.is_file() else {}
        return EngineJobOutput(output_uri=f"file://{video_path.resolve()}", engine_metadata=metadata)

    def cancel(self, handle: ComputeJobHandle) -> None:
        (self._output_dir / f"{handle.external_job_id}.mp4").unlink(missing_ok=True)
        (self._output_dir / f"{handle.external_job_id}.json").unlink(missing_ok=True)
