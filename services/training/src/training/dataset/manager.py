from __future__ import annotations

from .interfaces import ICaptionProvider, IDatasetValidator, IDuplicateDetector, ValidationResult
from .metadata import extract_clip_metadata
from .records import ClipRecord
from .split import split_dataset
from .statistics import DatasetStatistics, compute_statistics
from .versioning import DatasetVersion, build_dataset_version


class DatasetManager:
    """Orchestrates the dataset pipeline end-to-end over raw clip files:
    ingest (real ffprobe metadata + SHA-256 hash) -> caption -> validate
    -> find duplicates -> split -> statistics -> version. Every step is
    real, CPU-only work; the default providers (`HeuristicCaptionProvider`,
    `HashDuplicateDetector`) need no network access or trained model,
    though `ICaptionProvider`/`IDuplicateDetector` are real swap points
    for their Stage 4/3 real-model counterparts once those exist (Phase
    9 roadmap, docs/adr/0021-phase9-preparation.md) - exactly the same
    injected-interface shape `GenerationPipeline` uses for
    `IVideoEngine`/`IComputeProvider`.

    `clip_id` is derived from the file's content hash
    (`clip_<sha256[:16]>`), not an incrementing counter or the filename -
    re-ingesting the same bytes under a different filename or path
    always resolves to the same clip, which is also why
    `HashDuplicateDetector`'s job is finding *distinct files with
    identical content*, not re-ingested duplicates of the same file
    (those just overwrite the same record)."""

    def __init__(
        self,
        *,
        validator: IDatasetValidator,
        caption_provider: ICaptionProvider,
        duplicate_detector: IDuplicateDetector,
    ) -> None:
        self._validator = validator
        self._captions = caption_provider
        self._dedup = duplicate_detector
        self._records: dict[str, ClipRecord] = {}

    def ingest(self, source_uri: str, *, tags: list[str] | None = None, rights_cleared: bool = False) -> ClipRecord:
        metadata = extract_clip_metadata(source_uri)
        clip_id = f"clip_{metadata.file_hash[:16]}"
        record = ClipRecord(
            clip_id=clip_id,
            source_uri=source_uri,
            metadata=metadata,
            tags=list(tags or []),
            rights_cleared=rights_cleared,
        )
        self._records[clip_id] = record
        return record

    def caption(self, clip_id: str) -> ClipRecord:
        record = self._require(clip_id)
        record.caption = self._captions.generate_caption(record)
        return record

    def caption_all(self) -> None:
        for clip_id in list(self._records):
            self.caption(clip_id)

    def validate(self, clip_id: str) -> ValidationResult:
        return self._validator.validate(self._require(clip_id))

    def validate_all(self) -> dict[str, ValidationResult]:
        return {clip_id: self._validator.validate(record) for clip_id, record in self._records.items()}

    def find_duplicates(self, *, embeddings: dict[str, tuple[float, ...]] | None = None) -> list[tuple[str, str]]:
        return self._dedup.find_duplicates(list(self._records.values()), embeddings=embeddings)

    def split(
        self, *, val_fraction: float = 0.1, test_fraction: float = 0.1, seed: int = 0
    ) -> dict[str, list[ClipRecord]]:
        return split_dataset(
            list(self._records.values()), val_fraction=val_fraction, test_fraction=test_fraction, seed=seed
        )

    def statistics(self) -> DatasetStatistics:
        return compute_statistics(list(self._records.values()))

    def version(self) -> DatasetVersion:
        return build_dataset_version(list(self._records.values()))

    def records(self) -> list[ClipRecord]:
        return list(self._records.values())

    def get(self, clip_id: str) -> ClipRecord | None:
        return self._records.get(clip_id)

    def _require(self, clip_id: str) -> ClipRecord:
        record = self._records.get(clip_id)
        if record is None:
            raise KeyError(f"No such clip: {clip_id}")
        return record
