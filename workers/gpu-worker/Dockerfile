# GPU execution container run by RunPod Serverless / the Vast.ai job-runner.
# Phase 3: pin to the actual Wan2.1 repo commit and its CUDA/PyTorch version
# requirements once the real inference call in wan21_adapter.py is implemented.
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip git && \
    rm -rf /var/lib/apt/lists/*

# Phase 3: clone/vendor Wan2.1 (Apache-2.0) and install its requirements here.
# COPY requirements-wan21.txt .
# RUN pip3 install --no-cache-dir -r requirements-wan21.txt

COPY workers/gpu-worker/handler.py /workspace/handler.py

CMD ["python3", "handler.py"]
