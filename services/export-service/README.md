# services/export-service

## Export System

**Responsibility:** Produces final delivery artifacts from the assembled master: multiple formats (MP4/H.264, ProRes), multiple aspect-ratio crops for social platforms, thumbnails, upload to CDN/object storage, and webhook notification back to the API/Frontend.

**Input:** Assembled master video from Post-Processing

**Output:** One or more final delivery files on the CDN, plus a webhook event

**Consumed by:** Frontend / API caller

**Status:** Interface/package scaffolded in Phase 0. Business logic is a
Phase 5 target - see `docs/ARCHITECTURE.md#roadmap`.
