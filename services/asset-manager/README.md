# services/asset-manager

## Asset Manager

**Responsibility:** Owns the lifecycle of every user-uploaded and system-generated asset: reference images/videos, storyboard preview frames, LUTs, HDRIs. Issues signed URIs used throughout the schemas (`reference_asset_ids`, `conditioning_images`, `preview_image_asset_id`, ...) and enforces cleanup/retention policy.

**Input:** Uploads from the Frontend/API, and generated intermediate assets from other services

**Output:** Asset ids resolvable to signed storage URIs

**Consumed by:** Everything that references an asset id in a schema

**Status:** Interface/package scaffolded in Phase 0. Business logic is a
Phase 3 target - see `docs/ARCHITECTURE.md#roadmap`.
