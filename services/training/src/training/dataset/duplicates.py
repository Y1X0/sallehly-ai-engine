from __future__ import annotations

import math
from collections import defaultdict

from ..errors import ModelUnavailableError
from .interfaces import IDuplicateDetector
from .records import ClipRecord


class HashDuplicateDetector(IDuplicateDetector):
    """Real exact-duplicate detection via `ClipMetadata.file_hash`
    (SHA-256) - always available, no model needed. Catches byte-identical
    re-uploads (including re-uploads under a different filename); does
    NOT catch near-duplicates (the same footage re-encoded at a
    different bitrate, or two perceptually similar takes) - that needs
    `EmbeddingDuplicateDetector`."""

    def find_duplicates(
        self, records: list[ClipRecord], *, embeddings: dict[str, tuple[float, ...]] | None = None
    ) -> list[tuple[str, str]]:
        by_hash: dict[str, list[str]] = defaultdict(list)
        for record in records:
            by_hash[record.metadata.file_hash].append(record.clip_id)

        pairs: list[tuple[str, str]] = []
        for clip_ids in by_hash.values():
            for i in range(len(clip_ids)):
                for j in range(i + 1, len(clip_ids)):
                    pairs.append((clip_ids[i], clip_ids[j]))
        return pairs


class EmbeddingDuplicateDetector(IDuplicateDetector):
    """Near-duplicate detection via cosine similarity over precomputed
    perceptual embeddings. Comparing embeddings is pure math and needs
    no GPU - the pure-Python cosine similarity here is deliberately the
    same formula `cinematic_intelligence.model_adapters.embedding_providers`
    uses, not reimplemented as a shared dependency to keep
    `services/training` decoupled from `services/cinematic-intelligence`.
    *Producing* the embeddings, however, genuinely needs a real vision
    model (e.g. `ClipEmbeddingProvider`/`DinoEmbeddingProvider`) this
    environment doesn't have installed - so `find_duplicates` raises
    `ModelUnavailableError` if no `embeddings` were supplied, rather than
    silently skipping near-duplicate detection.
    """

    def __init__(self, threshold: float = 0.97) -> None:
        self._threshold = threshold

    def find_duplicates(
        self, records: list[ClipRecord], *, embeddings: dict[str, tuple[float, ...]] | None = None
    ) -> list[tuple[str, str]]:
        if not embeddings:
            raise ModelUnavailableError(
                "EmbeddingDuplicateDetector requires precomputed embeddings (clip_id -> vector) "
                "from a real embedding model - none were supplied. Compute them with a real "
                "IEmbeddingProvider (e.g. cinematic_intelligence.model_adapters.ClipEmbeddingProvider "
                "or DinoEmbeddingProvider against an extracted representative frame per clip) first."
            )

        clip_ids = [r.clip_id for r in records if r.clip_id in embeddings]
        pairs: list[tuple[str, str]] = []
        for i in range(len(clip_ids)):
            for j in range(i + 1, len(clip_ids)):
                similarity = _cosine_similarity(embeddings[clip_ids[i]], embeddings[clip_ids[j]])
                if similarity >= self._threshold:
                    pairs.append((clip_ids[i], clip_ids[j]))
        return pairs


def _cosine_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    if len(a) != len(b):
        raise ValueError(f"Embedding length mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))
