from __future__ import annotations

from abc import ABC, abstractmethod

from .records import ModelVersionRecord, PromotionStatus


class ModelRegistryError(Exception):
    """Base class for Model Registry failures - unknown version id,
    invalid promotion target, failed compatibility check."""


class UnknownModelVersionError(ModelRegistryError):
    pass


class IModelRegistry(ABC):
    """Version management, checkpoint metadata, promotion, and rollback
    for trained model checkpoints - the Phase 9 counterpart to
    `IProjectStore` (packages/persistence). A checkpoint produced by
    `ITrainer.train()` (trainer.py) only becomes a `ModelVersionRecord`
    here once someone deliberately decides it's worth evaluating for
    promotion - training and registration are separate, explicit steps,
    the same way `ProjectLifecycle.finalize_project` is a deliberate
    action past `COMPLETED`, not automatic.
    """

    @abstractmethod
    def register(self, record: ModelVersionRecord) -> None: ...

    @abstractmethod
    def get(self, version_id: str) -> ModelVersionRecord | None: ...

    @abstractmethod
    def list_all(self) -> list[ModelVersionRecord]: ...

    @abstractmethod
    def promote(self, version_id: str, target_status: PromotionStatus) -> ModelVersionRecord:
        """Advances `version_id` to `target_status`, enforcing the
        `registry.records`-defined promotion state machine
        (STAGING -> CANARY -> PRODUCTION, or REJECTED from either)."""

    @abstractmethod
    def get_production(self) -> ModelVersionRecord | None: ...

    @abstractmethod
    def rollback(self) -> ModelVersionRecord | None:
        """Reverts PRODUCTION to whichever version held it immediately
        before the current one, archiving the current one in the
        process. Returns the restored record, or `None` if there is no
        prior production version to revert to."""
