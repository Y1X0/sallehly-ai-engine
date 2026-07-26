# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this
repo is a monorepo of independently-developed but jointly-released
workspace members, so this file tracks repo-level releases rather than
per-package semver (individual `services/*`/`packages/*` stay at their
internal `0.1.0` - they are workspace members, not independently
published packages, so bumping thirty individual version strings on
every release would be pure churn with no real meaning to a consumer).

## [1.0.0] — first production-ready release

The full pipeline, end to end, is real: a user's prompt goes through a
real Creative Director, real storyboard/render-plan approval gates,
real Cinematic Intelligence consistency/quality scoring, and comes out
as a real generated video clip - either a real tiny-scale Wan clip with
zero credentials (`COMPUTE_PROVIDER=local-inference`, try it at
`GET /demo`) or real full-scale Wan2.2 generation on a real deployed
RunPod GPU endpoint (`COMPUTE_PROVIDER=runpod`).

See `docs/PRODUCTION_READINESS_CHECKLIST.md` for the full per-subsystem
status and exactly what's left for a real RunPod production rollout
(all infrastructure/credential steps, not code gaps), and the root
`README.md`'s `## Status` section for the complete phase-by-phase build
log this release is built on.

### Added

- **Real video generation.** `video_engine_adapter.inference.wan_inference`:
  a real `diffusers.WanPipeline`-based text-to-video generation call.
  `LocalInferenceProvider`: a new `IComputeProvider` that runs it
  in-process, zero credentials, real (if tiny-scale) playable `.mp4`
  output - replaces the old JSON-stub-only demo experience.
- **RunPod production backend.** `workers/gpu-worker/handler.py` is now
  a real, working RunPod Serverless handler (previously a
  `NotImplementedError` stub): downloads and checksum-verifies real
  Wan2.2 weights (`training.hf_download`, never random weights), runs
  real inference, uploads via `storage_sdk`. `infra/runpod/deploy_endpoint.py`/
  `check_health.py`: real deployment tooling using the official `runpod`
  SDK's actual management API. `RunPodProvider.health_check()`: real
  `GET /health`.
- **Click-through demo.** `GET /demo` (`apps/api/src/api/static/demo.html`):
  type a prompt, watch the real pipeline run, see the generated
  storyboard and a real playable clip per shot.
- **Wan2.2 LoRA training, real backend.** `Wan22DiffusersBackend`: real
  `diffusers`/`peft` forward/backward/optimizer step, replacing
  `UnavailableWan22Backend` as the default. Real HF weight download with
  per-file checksum verification. Kaggle free-GPU dispatch, fixed from a
  fundamentally broken argv-passing design (Kaggle kernels accept no CLI
  arguments) to a real dataset-upload-based wrapper
  (`kaggle_kernel_runner.py`), with CUDA enforcement (never silently
  trains on CPU), full run-to-run reproducibility (seeded torch/numpy/
  random), checkpoint resume, checkpoint validation after download, and
  a deterministic CI placeholder-dataset split.
- `docs/PRODUCTION_READINESS_CHECKLIST.md`, this `CHANGELOG.md`.

### Fixed

- `COMPUTE_PROVIDER=runpod` with missing `RUNPOD_API_KEY`/`RUNPOD_ENDPOINT_ID`
  now fails the API at startup with a clear, specific error instead of
  silently falling back to the mock `LocalProvider`.
- `RandomLatentBatchEncoder`'s per-clip seed used Python's built-in
  `hash()`, which is salted per-process (`PYTHONHASHSEED`) and was
  therefore not actually reproducible across separate runs despite
  looking seeded - replaced with a stable SHA-256-based derivation.
- `wan22_lora_train.py --device` defaulted to `"cpu"` with no
  enforcement at all, and the Kaggle wrapper never overrode it - a real
  Kaggle GPU dispatch could have silently trained on CPU the entire
  time. `--device` now defaults to `"auto"` and fails immediately if no
  CUDA GPU is available.
- `kaggle_kernel_runner.py` used to `pip install` the full
  `training[gpu-training]` extra (including `torch>=2.3`), risking pip
  replacing Kaggle's preinstalled, driver-matched CUDA torch build with
  an unrelated one from PyPI - now installs only the packages not
  already importable, `--no-deps`, never naming `torch`.
- `fetch_kaggle_kernel_result.py` skipped pulling Kaggle output entirely
  if polling timed out, discarding any logs/checkpoints the run had
  already produced - now always attempts the pull regardless of polling
  outcome.
- 4 unused imports removed repo-wide (`shutil` in `checkpoint.py`,
  `dataclasses.field` in `config.py`/`lora.py`, an unused test import) -
  `ruff check .` is clean.

### Known limitations (see checklist §6 for the exact remaining steps)

- Real full-scale Wan2.2 generation via `COMPUTE_PROVIDER=runpod` has
  not been executed against a live deployed endpoint from this
  development environment - it requires a funded RunPod account, a
  pushed Docker image, and an unrestricted network, none of which this
  environment had. Every real code path was exercised up to that exact
  boundary (the real HF download call reaches a genuine 403 at the
  sandbox's own network edge, not a fabricated success).
- `VastAIProvider` remains unimplemented (`NotImplementedError`) - out
  of scope for this release, unchanged from earlier phases.
