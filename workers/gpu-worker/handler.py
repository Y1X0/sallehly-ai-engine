"""RunPod Serverless handler entrypoint for the Wan2.2 GPU worker.

Receives the real `job` dict RunPod's serverless SDK passes to every
handler (`job["input"]` is the `EngineJobPayload.input` dict
`Wan21Adapter.build_job_payload`/a future Wan2.2 adapter produces - see
services/video-engine-adapter), runs real Wan2.2 inference, uploads the
resulting clip to configured storage, and returns
`{"output_uri": ..., "engine_metadata": {...}}` - the exact shape
`video_engine_adapter.compute.RunPodProvider.fetch_output()` already
expects (`output.get("output_uri")`/`output.get("engine_metadata")`).

Real Wan2.2 weights are downloaded once per worker process (kept warm
across invocations by RunPod between cold starts) via
`training.hf_download` - the same checksum-verified download machinery
`services/training/scripts/download_wan22_weights.py` uses, per the
real registry entry in `models/registry.yaml`. This never fabricates or
randomly initializes weights: if the download or its checksum
verification fails, `run()` lets the real exception propagate, which
RunPod's own SDK (confirmed from the installed `runpod` package's
`serverless/modules/rp_job.py::run_job`) catches and reports as a real
job failure with the real error message and traceback - never a silent
success.

Any RunPod-compatible caller can invoke this; the Vast.ai job-runner
(Phase 3, infra/vastai/) would call `run()` with the same
`{"id": ..., "input": {...}}` shape directly, without the `runpod` SDK
wrapper below.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

_ENGINE_ID = os.environ.get("WAN22_ENGINE_ID", "wan2.2-ti2v-5b")
_REGISTRY_PATH = os.environ.get("WAN22_REGISTRY_PATH", "models/registry.yaml")
_MODELS_CACHE_ROOT = os.environ.get("WAN22_MODELS_CACHE_ROOT", "/runpod-volume/models-cache")
_OUTPUT_DIR = Path(os.environ.get("WAN22_OUTPUT_DIR", "/tmp/wan22-output"))
_DEVICE = os.environ.get("WAN22_DEVICE", "cuda")

_cached_model_dir: str | None = None


def _ensure_weights_downloaded() -> str:
    """Downloads (once per warm worker process) and verifies real Wan2.2
    weights - never random weights. Reuses the exact same real,
    checksum-verified download machinery
    `services/training/scripts/download_wan22_weights.py` uses (see
    `training.hf_download`), so this worker and the LoRA training
    pipeline share one source of truth for what "verified real weights"
    means. `HF_TOKEN`, if the configured repo is gated, must be set as a
    real environment variable on this worker (RunPod: attach it as a
    Secret) - never hardcoded here.
    """
    global _cached_model_dir
    if _cached_model_dir is not None:
        return _cached_model_dir

    from training import HuggingFaceWeightsDownloader, load_wan22_registry_entries, resolve_local_weights

    manifest = resolve_local_weights(_ENGINE_ID, cache_root=_MODELS_CACHE_ROOT)
    if manifest is not None:
        manifest.verify()
    else:
        registry_entries = load_wan22_registry_entries(_REGISTRY_PATH)
        entry = registry_entries.get(_ENGINE_ID)
        if entry is None:
            raise RuntimeError(
                f"No Wan2.2 registry entry with a download: block for engine_id={_ENGINE_ID!r} in "
                f"{_REGISTRY_PATH}. Known entries: {sorted(registry_entries)}"
            )
        downloader = HuggingFaceWeightsDownloader(
            cache_root=_MODELS_CACHE_ROOT, hf_token=os.environ.get("HF_TOKEN"),
        )
        manifest = downloader.download(entry)
        manifest.verify()

    _cached_model_dir = manifest.local_dir
    return _cached_model_dir


def _build_storage_provider() -> Any:
    """Mirrors apps/api/src/api/state.py's own storage-provider
    selection (same STORAGE_PROVIDER/STORAGE_* env vars) so this worker
    and the API agree on one storage convention - "local" only makes
    sense here if the local provider's root is a RunPod network volume
    actually mounted on this worker; real production deployments should
    set STORAGE_PROVIDER=s3."""
    if os.environ.get("STORAGE_PROVIDER") == "s3":
        from storage_sdk import S3Provider

        return S3Provider(
            os.environ.get("STORAGE_BUCKET", "video-engine-assets"),
            endpoint_url=os.environ.get("STORAGE_ENDPOINT_URL") or None,
            access_key=os.environ.get("STORAGE_ACCESS_KEY") or None,
            secret_key=os.environ.get("STORAGE_SECRET_KEY") or None,
        )
    from storage_sdk import LocalFilesystemStorageProvider

    return LocalFilesystemStorageProvider(os.environ.get("STORAGE_LOCAL_ROOT", "/runpod-volume/storage"))


def run(job: dict[str, Any]) -> dict[str, Any]:
    """The real RunPod Serverless handler contract: `job` is the full
    RunPod job dict (`job["id"]`, `job["input"]`, ...), confirmed
    against the installed `runpod` package's own
    `serverless/modules/rp_job.py::run_job` (`handler(job)`, not
    `handler(job["input"])` - the previous stub here had this wrong)."""
    job_input = job["input"]
    job_id = job.get("id", uuid.uuid4().hex)

    model_dir = _ensure_weights_downloaded()

    from video_engine_adapter.inference import generate_video

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    local_path = _OUTPUT_DIR / f"{job_id}.mp4"
    metadata = generate_video(
        job_input, output_path=local_path, smoke_test=False, model_id=model_dir, device=_DEVICE,
    )

    storage = _build_storage_provider()
    output_uri = storage.put(f"generated/{job_id}.mp4", str(local_path))

    return {"output_uri": output_uri, "engine_metadata": metadata}


if __name__ == "__main__":
    try:
        import runpod  # type: ignore[import-not-found]

        runpod.serverless.start({"handler": run})
    except ImportError:
        raise SystemExit("Add the `runpod` package to this image's dependencies (see workers/gpu-worker/Dockerfile).")
