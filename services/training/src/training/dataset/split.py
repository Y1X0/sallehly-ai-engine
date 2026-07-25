from __future__ import annotations

import hashlib

from .records import ClipRecord

_HEX_MAX = 0xFFFFFFFF


def assign_split(clip_id: str, *, val_fraction: float = 0.1, test_fraction: float = 0.1, seed: int = 0) -> str:
    """Deterministic train/val/test assignment via a stable hash of
    `f"{seed}:{clip_id}"`, not Python's `random` module - the same
    `clip_id` always lands in the same split, on any machine, in any
    process, without persisting the assignment anywhere. This matters
    for the Phase 9 roadmap's Stage 8 benchmarking gate: a golden test
    set can always be reproduced from `clip_id`s alone, and adding new
    clips to the pool never reshuffles which existing clips are "test" -
    a real risk with seeded-`random.shuffle`-based splitting, where
    inserting or removing even one clip changes every subsequent draw.
    """
    if not (0.0 <= val_fraction < 1.0):
        raise ValueError(f"val_fraction must be in [0.0, 1.0), got {val_fraction}")
    if not (0.0 <= test_fraction < 1.0):
        raise ValueError(f"test_fraction must be in [0.0, 1.0), got {test_fraction}")
    if val_fraction + test_fraction >= 1.0:
        raise ValueError(
            f"val_fraction + test_fraction must be < 1.0, got {val_fraction} + {test_fraction} = "
            f"{val_fraction + test_fraction}"
        )

    digest = hashlib.sha256(f"{seed}:{clip_id}".encode()).hexdigest()
    bucket = int(digest[:8], 16) / _HEX_MAX

    if bucket < test_fraction:
        return "test"
    if bucket < test_fraction + val_fraction:
        return "val"
    return "train"


def split_dataset(
    records: list[ClipRecord], *, val_fraction: float = 0.1, test_fraction: float = 0.1, seed: int = 0
) -> dict[str, list[ClipRecord]]:
    """Splits and also stamps `record.split` on every record in place -
    the same "compute and record the result" shape `ProjectLifecycle`
    uses for state transitions, so a caller never has to remember to
    apply `assign_split`'s result back onto the record themselves."""
    grouped: dict[str, list[ClipRecord]] = {"train": [], "val": [], "test": []}
    for record in records:
        split = assign_split(record.clip_id, val_fraction=val_fraction, test_fraction=test_fraction, seed=seed)
        record.split = split
        grouped[split].append(record)
    return grouped
