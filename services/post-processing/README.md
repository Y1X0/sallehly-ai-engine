# services/post-processing

## Post-Processing

**Responsibility:** Stitches all of a project's RawClips into one timeline: transitions, frame interpolation, upscaling, color grade application, audio/music/TTS mixing, subtitles, watermarking.

**Input:** Ordered list of `RawClip` for a project

**Output:** One assembled, graded, mixed master video file

**Consumed by:** Export Service

**Status:** Interface/package scaffolded in Phase 0. Business logic is a
Phase 5 target - see `docs/ARCHITECTURE.md#roadmap`.
