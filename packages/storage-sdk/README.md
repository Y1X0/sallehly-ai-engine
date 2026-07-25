# packages/storage-sdk

`IStorageProvider` - where the platform persists bytes it owns
(post-processed masters, thumbnails, exported deliverables). Two
implementations, selected via `Settings.storage_provider` (`"local"`
default / `"s3"`, `apps/api/state.py`):

- **`LocalFilesystemStorageProvider`**: copies into a local directory,
  returns `file://` URIs. The default for every test in this repo and
  local dev with no object storage running.
- **`S3Provider`** (Phase 8 WP4, `s3_provider.py`): a real S3-compatible
  backend via `boto3` (`endpoint_url` makes it work against AWS S3,
  MinIO, R2, or anything else speaking the S3 REST API), returns
  `s3://<bucket>/<key>` URIs. See
  `docs/adr/0018-s3-storage-provider.md`.

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

## Status (Phase 8)

`LocalFilesystemStorageProvider` (Phase 3) and `S3Provider` (Phase 8
WP4) are both implemented; either can back `AssetManager` via
`STORAGE_PROVIDER=local|s3`. `S3Provider` is tested against `moto`'s
`ThreadedMotoServer` - a real, separately-running S3-REST-API HTTP
server - rather than a live MinIO/S3 endpoint, since neither is
reachable in this sandbox (`tests/test_s3_provider.py`); see
`docs/adr/0018-s3-storage-provider.md` for why, and for the honest
rigor-tier caveat that implies for a genuine production deployment.
