"""Phase 9 Preparation: the dataset pipeline - real ffprobe-based
metadata extraction (via real synthetic clips, media_helpers.py, same
convention as Phase 6's post-processing tests), validation, captioning,
duplicate detection, splitting, statistics, and versioning. All CPU-only;
no GPU or trained model required for anything exercised here - see
docs/adr/0021-phase9-preparation.md.
"""

from __future__ import annotations

import pytest
from media_helpers import FFMPEG_AVAILABLE, make_color_clip, make_tone
from training import (
    ClipMetadata,
    ClipRecord,
    DatasetManager,
    DatasetValidator,
    EmbeddingDuplicateDetector,
    FilesystemDatasetVersionStore,
    HashDuplicateDetector,
    HeuristicCaptionProvider,
    ModelUnavailableError,
    VLMCaptionProvider,
    assign_split,
    build_dataset_version,
    compute_statistics,
    compute_version_id,
    extract_clip_metadata,
    split_dataset,
)

pytestmark_ffmpeg = pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed")


def _metadata(**overrides) -> ClipMetadata:
    base = dict(duration_sec=5.0, width=1280, height=720, fps=24.0, codec="h264", size_bytes=1_000_000, file_hash="a" * 64)
    base.update(overrides)
    return ClipMetadata(**base)


def _clip_record(clip_id: str = "clip_1", **overrides) -> ClipRecord:
    metadata_overrides = overrides.pop("metadata_overrides", {})
    base = dict(clip_id=clip_id, source_uri=f"file:///tmp/{clip_id}.mp4", metadata=_metadata(**metadata_overrides))
    base.update(overrides)
    return ClipRecord(**base)


# --- extract_clip_metadata (real ffprobe execution) ----------------------


@pytestmark_ffmpeg
def test_extract_clip_metadata_reads_real_ffprobe_facts(tmp_path):
    clip_path = tmp_path / "red.mp4"
    make_color_clip(clip_path, "red", duration=2.0, size="320x240", rate=24)

    metadata = extract_clip_metadata(str(clip_path))

    assert 1.9 <= metadata.duration_sec <= 2.1
    assert metadata.width == 320
    assert metadata.height == 240
    assert metadata.fps == 24.0
    assert metadata.codec == "h264"
    assert metadata.size_bytes > 0
    assert len(metadata.file_hash) == 64
    assert metadata.resolution == "320x240"


@pytestmark_ffmpeg
def test_extract_clip_metadata_same_bytes_produce_same_hash(tmp_path):
    path_a = tmp_path / "a.mp4"
    path_b = tmp_path / "b.mp4"
    make_color_clip(path_a, "blue", duration=1.0, size="160x120", rate=24)
    # Re-encoding with identical parameters twice from the same lavfi
    # source produces byte-identical output - a real (not simulated)
    # duplicate for HashDuplicateDetector to catch.
    make_color_clip(path_b, "blue", duration=1.0, size="160x120", rate=24)

    hash_a = extract_clip_metadata(str(path_a)).file_hash
    hash_b = extract_clip_metadata(str(path_b)).file_hash
    assert hash_a == hash_b


@pytestmark_ffmpeg
def test_extract_clip_metadata_raises_on_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract_clip_metadata(str(tmp_path / "does-not-exist.mp4"))


@pytestmark_ffmpeg
def test_extract_clip_metadata_raises_when_no_video_stream(tmp_path):
    audio_path = tmp_path / "tone.aac"
    make_tone(audio_path, duration=1.0)
    with pytest.raises(ValueError):
        extract_clip_metadata(str(audio_path))


def test_clip_metadata_round_trips_through_dict():
    metadata = _metadata()
    restored = ClipMetadata.from_dict(metadata.to_dict())
    assert restored == metadata


def test_clip_record_round_trips_through_dict():
    record = _clip_record(caption="a caption", split="train", tags=["product-shot"], rights_cleared=True)
    restored = ClipRecord.from_dict(record.to_dict())
    assert restored == record


# --- DatasetValidator -----------------------------------------------------


def test_dataset_validator_accepts_a_clean_clip():
    record = _clip_record(rights_cleared=True, caption="a real caption")
    result = DatasetValidator().validate(record)
    assert result.valid is True
    assert not any(i.severity == "error" for i in result.issues)


def test_dataset_validator_flags_missing_rights_clearance():
    record = _clip_record(rights_cleared=False, caption="captioned")
    result = DatasetValidator().validate(record)
    assert result.valid is False
    assert any(i.field == "rights_cleared" and i.severity == "error" for i in result.issues)


@pytest.mark.parametrize(
    "metadata_overrides",
    [
        {"duration_sec": 0.01},  # below floor
        {"duration_sec": 999.0},  # above ceiling
        {"height": 100},  # below resolution floor
        {"fps": 5.0},  # below fps floor
    ],
)
def test_dataset_validator_flags_out_of_range_metadata(metadata_overrides):
    record = _clip_record(rights_cleared=True, caption="captioned", metadata_overrides=metadata_overrides)
    result = DatasetValidator().validate(record)
    assert result.valid is False


def test_dataset_validator_treats_missing_caption_as_warning_by_default():
    record = _clip_record(rights_cleared=True, caption=None)
    result = DatasetValidator().validate(record)
    assert result.valid is True
    assert any(i.field == "caption" and i.severity == "warning" for i in result.issues)


def test_dataset_validator_can_require_caption_as_an_error():
    record = _clip_record(rights_cleared=True, caption=None)
    result = DatasetValidator(require_caption=True).validate(record)
    assert result.valid is False
    assert any(i.field == "caption" and i.severity == "error" for i in result.issues)


# --- Caption providers ------------------------------------------------


def test_heuristic_caption_provider_produces_a_nonempty_deterministic_caption():
    record = _clip_record(tags=["product-shot", "handheld"])
    caption = HeuristicCaptionProvider().generate_caption(record)
    assert "product-shot" in caption
    assert "720" in caption
    assert HeuristicCaptionProvider().generate_caption(record) == caption  # deterministic


def test_vlm_caption_provider_raises_model_unavailable_error():
    with pytest.raises(ModelUnavailableError):
        VLMCaptionProvider().generate_caption(_clip_record())


# --- Duplicate detectors ------------------------------------------------


def test_hash_duplicate_detector_finds_exact_duplicates():
    a = _clip_record("clip_a", metadata_overrides={"file_hash": "same" * 16})
    b = _clip_record("clip_b", metadata_overrides={"file_hash": "same" * 16})
    c = _clip_record("clip_c", metadata_overrides={"file_hash": "diff" * 16})

    pairs = HashDuplicateDetector().find_duplicates([a, b, c])
    assert pairs == [("clip_a", "clip_b")]


def test_hash_duplicate_detector_finds_nothing_when_all_hashes_differ():
    a = _clip_record("clip_a", metadata_overrides={"file_hash": "a" * 64})
    b = _clip_record("clip_b", metadata_overrides={"file_hash": "b" * 64})
    assert HashDuplicateDetector().find_duplicates([a, b]) == []


def test_embedding_duplicate_detector_requires_embeddings():
    with pytest.raises(ModelUnavailableError):
        EmbeddingDuplicateDetector().find_duplicates([_clip_record("clip_a"), _clip_record("clip_b")])


def test_embedding_duplicate_detector_finds_near_duplicates_above_threshold():
    a, b, c = _clip_record("clip_a"), _clip_record("clip_b"), _clip_record("clip_c")
    embeddings = {
        "clip_a": (1.0, 0.0),
        "clip_b": (0.999, 0.001),  # nearly identical direction to a
        "clip_c": (0.0, 1.0),  # orthogonal to a/b
    }
    pairs = EmbeddingDuplicateDetector(threshold=0.99).find_duplicates([a, b, c], embeddings=embeddings)
    assert pairs == [("clip_a", "clip_b")]


# --- split ----------------------------------------------------------------


def test_assign_split_is_deterministic():
    first = assign_split("clip_xyz", val_fraction=0.1, test_fraction=0.1, seed=0)
    second = assign_split("clip_xyz", val_fraction=0.1, test_fraction=0.1, seed=0)
    assert first == second
    assert first in ("train", "val", "test")


def test_assign_split_differs_across_seeds_for_at_least_some_ids():
    ids = [f"clip_{i}" for i in range(50)]
    splits_seed_0 = [assign_split(cid, seed=0) for cid in ids]
    splits_seed_1 = [assign_split(cid, seed=1) for cid in ids]
    assert splits_seed_0 != splits_seed_1


def test_assign_split_respects_fractions_at_scale():
    ids = [f"clip_{i}" for i in range(2000)]
    counts = {"train": 0, "val": 0, "test": 0}
    for cid in ids:
        counts[assign_split(cid, val_fraction=0.1, test_fraction=0.2, seed=7)] += 1
    # Not an exact match (hash-based, not a perfect partition) but should
    # land close to the requested fractions at this sample size.
    assert 0.6 < counts["train"] / len(ids) < 0.8
    assert 0.05 < counts["val"] / len(ids) < 0.15
    assert 0.15 < counts["test"] / len(ids) < 0.25


def test_assign_split_rejects_invalid_fractions():
    with pytest.raises(ValueError):
        assign_split("clip_1", val_fraction=0.6, test_fraction=0.6)
    with pytest.raises(ValueError):
        assign_split("clip_1", val_fraction=-0.1)


def test_split_dataset_stamps_record_split_and_groups_consistently():
    records = [_clip_record(f"clip_{i}") for i in range(20)]
    grouped = split_dataset(records, val_fraction=0.2, test_fraction=0.2, seed=3)

    assert set(grouped) == {"train", "val", "test"}
    for split_name, split_records in grouped.items():
        for record in split_records:
            assert record.split == split_name
    assert sum(len(v) for v in grouped.values()) == len(records)


# --- statistics -------------------------------------------------------


def test_compute_statistics_on_empty_list():
    stats = compute_statistics([])
    assert stats.clip_count == 0
    assert stats.total_duration_sec == 0.0
    assert stats.caption_coverage == 0.0


def test_compute_statistics_aggregates_real_values():
    records = [
        _clip_record("clip_1", caption="c1", rights_cleared=True, metadata_overrides={"duration_sec": 4.0, "height": 720, "fps": 24.0}),
        _clip_record("clip_2", caption=None, rights_cleared=False, metadata_overrides={"duration_sec": 6.0, "height": 1080, "fps": 30.0}),
    ]
    records[0].split = "train"
    records[1].split = "val"

    stats = compute_statistics(records)

    assert stats.clip_count == 2
    assert stats.total_duration_sec == 10.0
    assert stats.mean_duration_sec == 5.0
    assert stats.split_counts == {"train": 1, "val": 1}
    assert stats.caption_coverage == 0.5
    assert stats.rights_cleared_fraction == 0.5


# --- versioning -------------------------------------------------------


def test_compute_version_id_is_deterministic_and_order_independent():
    a = _clip_record("clip_a", metadata_overrides={"file_hash": "1" * 64})
    b = _clip_record("clip_b", metadata_overrides={"file_hash": "2" * 64})

    assert compute_version_id([a, b]) == compute_version_id([b, a])


def test_compute_version_id_changes_when_content_changes():
    a = _clip_record("clip_a", metadata_overrides={"file_hash": "1" * 64})
    b = _clip_record("clip_a", metadata_overrides={"file_hash": "2" * 64})  # same id, different content
    assert compute_version_id([a]) != compute_version_id([b])


def test_build_dataset_version_reflects_the_records_given():
    records = [_clip_record("clip_a"), _clip_record("clip_b")]
    version = build_dataset_version(records)
    assert version.clip_ids == ("clip_a", "clip_b")
    assert version.statistics.clip_count == 2


def test_filesystem_dataset_version_store_persists_across_instances(tmp_path):
    version = build_dataset_version([_clip_record("clip_a")])
    store = FilesystemDatasetVersionStore(tmp_path)
    store.save(version)

    reopened = FilesystemDatasetVersionStore(tmp_path)
    restored = reopened.get(version.version_id)
    assert restored is not None
    assert restored.clip_ids == version.clip_ids
    assert reopened.list_all() == [restored]


# --- DatasetManager end-to-end (real ffmpeg execution) ------------------


@pytestmark_ffmpeg
def test_dataset_manager_end_to_end_pipeline(tmp_path):
    clip_a = tmp_path / "a.mp4"
    clip_b = tmp_path / "b.mp4"
    clip_c_duplicate_of_a = tmp_path / "a_reupload.mp4"
    make_color_clip(clip_a, "green", duration=2.0, size="320x240", rate=24)
    make_color_clip(clip_b, "yellow", duration=3.0, size="320x240", rate=24)
    make_color_clip(clip_c_duplicate_of_a, "green", duration=2.0, size="320x240", rate=24)

    manager = DatasetManager(
        validator=DatasetValidator(min_duration_sec=0.1, min_height=100, min_fps=1.0),
        caption_provider=HeuristicCaptionProvider(),
        duplicate_detector=HashDuplicateDetector(),
    )

    record_a = manager.ingest(str(clip_a), tags=["product"], rights_cleared=True)
    manager.ingest(str(clip_b), tags=["lifestyle"], rights_cleared=True)
    record_c = manager.ingest(str(clip_c_duplicate_of_a), tags=["product"], rights_cleared=True)

    # Byte-identical re-encode resolves to the same content-addressed
    # clip_id as the original - ingesting it again is a no-op record
    # update, not a new distinct entry.
    assert record_c.clip_id == record_a.clip_id
    assert len(manager.records()) == 2

    manager.caption_all()
    validations = manager.validate_all()
    assert all(result.valid for result in validations.values())

    duplicates = manager.find_duplicates()
    assert duplicates == []  # the only real duplicate collapsed into one record above

    grouped = manager.split(val_fraction=0.0, test_fraction=0.0, seed=1)
    assert len(grouped["train"]) == 2

    stats = manager.statistics()
    assert stats.clip_count == 2
    assert stats.caption_coverage == 1.0
    assert stats.rights_cleared_fraction == 1.0

    version = manager.version()
    assert len(version.clip_ids) == 2
    assert version.version_id == compute_version_id(manager.records())


def test_dataset_manager_raises_key_error_for_unknown_clip():
    manager = DatasetManager(
        validator=DatasetValidator(),
        caption_provider=HeuristicCaptionProvider(),
        duplicate_detector=HashDuplicateDetector(),
    )
    with pytest.raises(KeyError):
        manager.caption("does-not-exist")
