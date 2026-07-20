# packages/storage-sdk

`IStorageProvider` - where the platform persists bytes it owns
(post-processed masters, thumbnails, exported deliverables). Local dev
uses `LocalFilesystemStorageProvider` (copies into a local directory,
returns `file://` URIs); production would add an S3/R2-backed
implementation with the same interface.

## Not the same thing as the Asset Manager

`services/asset-manager`'s `AssetManager` tracks *metadata about* an
asset (its id, versions, URIs) regardless of which storage backend holds
the bytes. Most Phase 3 assets (a `RawClip` fresh out of a Video Engine
Adapter) already live wherever the `IComputeProvider` uploaded them and
are registered with `AssetManager` via that existing URI, without ever
touching `IStorageProvider` - this interface is for the cases where the
platform itself needs to copy/persist something (e.g. a Post-Processing
master, Phase 5).

## Interface

```
IStorageProvider.put(key, source_path) -> uri
IStorageProvider.get_uri(key) -> uri
IStorageProvider.exists(key) -> bool
```

## Status (Phase 3)

`LocalFilesystemStorageProvider` implemented. An S3/R2-backed
implementation is a Phase 5+ concern (Post-Processing needs it first).
