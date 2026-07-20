from __future__ import annotations

from abc import ABC, abstractmethod

from .types import ComputeJobHandle, ComputeJobStatus, EngineJobOutput, EngineJobPayload


class IComputeProvider(ABC):
    """The infrastructure-agnostic execution contract.

    Defines WHERE an EngineJobPayload actually runs. Phase 0-3 target
    RunPod Serverless and rented Vast.ai instances (see
    docs/adr/0005-gpu-provider-runpod-vastai-first.md); Kubernetes GPU
    pools are a later IComputeProvider implementation, added without
    touching IVideoEngine, the Compiler, or anything above it.
    """

    @abstractmethod
    def submit(self, payload: EngineJobPayload) -> ComputeJobHandle: ...

    @abstractmethod
    def get_status(self, handle: ComputeJobHandle) -> ComputeJobStatus: ...

    @abstractmethod
    def fetch_output(self, handle: ComputeJobHandle) -> EngineJobOutput: ...

    @abstractmethod
    def cancel(self, handle: ComputeJobHandle) -> None: ...
