# GPU execution container run by RunPod Serverless / the Vast.ai job-runner.
# Runs real Wan2.2 inference via video_engine_adapter.inference.wan_inference
# (a real diffusers WanPipeline) - see handler.py.
#
# Build from the REPO ROOT (not this directory), so the COPY lines below
# can reach the packages this image needs:
#   docker build -f workers/gpu-worker/Dockerfile -t <your-registry>/sallehly-wan22-worker:2.2.0 .
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip git && \
    rm -rf /var/lib/apt/lists/*

# Real dependencies, baked in at build time (no network access needed at
# container startup beyond the real Wan2.2 weights download itself,
# handled by handler.py):
#   - runpod: the official RunPod Serverless worker SDK (real,
#     pip-installable - see infra/runpod/deploy_endpoint.py for how this
#     image is deployed to a real endpoint using this same SDK).
#   - This repo's own real code: video_engine_adapter.inference.generate_video
#     (the actual inference call) and training.hf_download (the real,
#     checksum-verified Wan2.2 weight download handler.py reuses - the
#     same machinery services/training/scripts/download_wan22_weights.py
#     uses, so there is exactly one source of truth for what "verified
#     real weights" means across training and inference).
COPY packages/video-engine-sdk /workspace/packages/video-engine-sdk
COPY packages/storage-sdk /workspace/packages/storage-sdk
COPY packages/config-sdk /workspace/packages/config-sdk
COPY services/video-engine-adapter /workspace/services/video-engine-adapter
COPY services/training /workspace/services/training
COPY models/registry.yaml /workspace/models/registry.yaml

RUN pip3 install --no-cache-dir runpod \
    -e /workspace/packages/video-engine-sdk \
    -e /workspace/packages/storage-sdk \
    -e /workspace/packages/config-sdk \
    -e "/workspace/services/video-engine-adapter[real-inference]" \
    -e "/workspace/services/training[gpu-training]"

COPY workers/gpu-worker/handler.py /workspace/handler.py

# handler.py's WAN22_REGISTRY_PATH default ("models/registry.yaml") is
# relative to WORKDIR - kept in sync with the COPY above.
ENV WAN22_REGISTRY_PATH=/workspace/models/registry.yaml

CMD ["python3", "handler.py"]
