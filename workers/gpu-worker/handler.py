"""RunPod Serverless handler entrypoint for the Wan2.1 GPU worker.

Receives the `input` dict built by Wan21Adapter.build_job_payload
(see services/video-engine-adapter), runs Wan2.1 inference, uploads the
result to object storage, and returns its URI. The same handler function
is reused by the Vast.ai job-runner service (infra/vastai/, Phase 3) so
there is exactly one place that knows how to actually invoke Wan2.1.
"""

from __future__ import annotations

from typing import Any


def run(job_input: dict[str, Any]) -> dict[str, Any]:
    raise NotImplementedError(
        "Phase 3: load Wan2.1 once at process start (kept warm across "
        "invocations), run inference with job_input's prompt/negative_prompt/"
        "width/height/num_frames/fps/seed/motion_strength/conditioning_images, "
        "upload the resulting clip to the configured bucket, and return "
        "{'output_uri': ..., 'engine_metadata': {...}}."
    )


if __name__ == "__main__":
    try:
        import runpod  # type: ignore[import-not-found]

        runpod.serverless.start({"handler": run})
    except ImportError:
        raise SystemExit(
            "Phase 3: add the `runpod` package to this image's dependencies."
        )
