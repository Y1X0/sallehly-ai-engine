# services/asset-manager

## Asset Manager

**Responsibility:** registry for every generated or uploaded asset
(video clips, preview images, metadata blobs) with per-key versioning.
Records *where* an asset lives (a `RawClip.storage_uri`, wherever the
`IComputeProvider`/`IVideoEngine` already put it, or a locally-uploaded
reference file) rather than moving bytes itself - see
`packages/storage-sdk` for the interface used when the platform *does*
need to copy/persist bytes (Phase 5+, Post-Processing).

**Input:** a `RawClip` (from `GenerationPipeline`) or any `(project_id, kind, uri)` to register

**Output:** `asset_record.schema.json` - an `asset_id` with a version history

**Consumed by:** `services/render-orchestrator` (`GenerationPipeline` registers each completed shot's video), Frontend/API (asset lookup by id)

## Interface

```python
manager = AssetManager()
record = manager.register_video(project_id="proj_1", shot_id="shot_0_0", raw_clip=raw_clip)
manager.get(record["asset_id"])
manager.latest_uri("proj_1", kind="video", shot_id="shot_0_0")
```

Registering the same `(project_id, shot_id, kind)` again appends a new
version rather than overwriting - re-rendering a shot keeps its history.

## Status (Phase 3)

Implemented as an in-memory registry (`AssetManager`). A persistent
(Postgres-backed) implementation is a later concern once `apps/api` has
a database layer - the registration/versioning shape here would not
change, only where it's stored.
