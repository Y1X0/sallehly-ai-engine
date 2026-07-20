# services/camera-engine

## Camera Engine (Camera Planner)

**Responsibility:** Chooses lens (focal length equivalent), angle, and camera movement (pan/tilt/dolly/crane/handheld/static/...) for each shot, driven by its storytelling intent rather than a fixed rotation of shot types.

**Input:** `shot.schema.json` (description, shot_type, duration_sec)

**Output:** Populates `shot.camera` (`camera.schema.json`)

**Consumed by:** Motion Engine

**Status:** Interface/package scaffolded in Phase 0. Business logic is a
Phase 2 target - see `docs/ARCHITECTURE.md#roadmap`.
