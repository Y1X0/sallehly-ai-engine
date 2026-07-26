from __future__ import annotations

from ..checkpoint import CheckpointRecord, ICheckpointStore


class PairedCheckpointMissingError(Exception):
    """Raised when a step's checkpoint set is incomplete - some, but not
    all, of a Wan2.2 run's required experts have a saved checkpoint for
    that step. A Wan2.2 A14B checkpoint is only usable once every expert
    has been saved for the same step (the fine-tuning blueprint's
    central risk: training/saving only one expert produces an
    incoherent model), so this is treated as a hard error, not a
    partial result."""


def expert_checkpoint_id(run_id: str, step: int, expert: str) -> str:
    return f"ckpt_{run_id}_{step:06d}_{expert}"


class Wan22CheckpointWriter:
    """Thin wrapper over the existing `ICheckpointStore` (no new storage
    mechanism - reuses `FilesystemCheckpointStore`/`InMemoryCheckpointStore`
    exactly as built in Phase 9 Preparation) that encodes the expert name
    into the checkpoint id and can verify a full expert set exists for a
    given step before considering that step's checkpoint complete."""

    def __init__(self, checkpoint_store: ICheckpointStore) -> None:
        self._store = checkpoint_store

    def save_expert_checkpoint(
        self,
        *,
        run_id: str,
        step: int,
        expert: str,
        artifact_uri: str,
        size_bytes: int = 0,
        metrics: dict[str, float] | None = None,
    ) -> str:
        checkpoint_id = expert_checkpoint_id(run_id, step, expert)
        self._store.save(
            CheckpointRecord(
                checkpoint_id=checkpoint_id,
                run_id=run_id,
                step=step,
                artifact_uri=artifact_uri,
                size_bytes=size_bytes,
                metrics=metrics or {},
            )
        )
        return checkpoint_id

    def get_paired_checkpoints(
        self, run_id: str, step: int, expected_experts: frozenset[str] | set[str]
    ) -> dict[str, CheckpointRecord]:
        found: dict[str, CheckpointRecord] = {}
        for expert in expected_experts:
            record = self._store.get(expert_checkpoint_id(run_id, step, expert))
            if record is not None:
                found[expert] = record

        missing = set(expected_experts) - set(found)
        if missing:
            raise PairedCheckpointMissingError(
                f"run {run_id!r} step {step} is missing checkpoints for experts "
                f"{sorted(missing)} (found: {sorted(found)})"
            )
        return found

    def latest_paired_step(
        self, run_id: str, expected_experts: frozenset[str] | set[str]
    ) -> int | None:
        """The highest step at which every expert in `expected_experts`
        has a saved checkpoint - the step a resumed run should continue
        from. Returns None if no step has a complete set yet (a fresh
        run, or a run where only some experts ever got checkpointed)."""
        steps = sorted({record.step for record in self._store.list_for_run(run_id)}, reverse=True)
        for step in steps:
            try:
                self.get_paired_checkpoints(run_id, step, expected_experts)
            except PairedCheckpointMissingError:
                continue
            return step
        return None
