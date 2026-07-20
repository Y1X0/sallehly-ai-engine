# services/camera-engine

## Camera Director (Camera Engine)

**Responsibility:** deterministic camera planning for every shot: shot
type, angle, lens (focal length equivalent), movement, and depth of
field. Follows a standard cinematography convention - a multi-shot scene
opens on a wide establishing shot, closes on a tight detail shot, and
rotates through medium framings in between - rather than an LLM call,
since the creative intent was already decided by the Story Planner/Scene
Generator; this stage is a mechanical translation of scene structure into
camera parameters.

**Input:** `shot.schema.json` (description, order) + the shot's position within its scene (first/middle/last/only)

**Output:** populates `shot.camera` (`camera.schema.json`)

**Consumed by:** Motion Director (mirrors camera easing into subject
motion), Storyboard Generator (renders it into human-readable text),
Render Configuration Compiler (embeds it in `render_configuration.schema.json`)

## Status (Phase 2)

Implemented as `CameraDirector.plan_camera(shot, position)`. Orchestrated
by `services/creative-compiler`, which computes each shot's `position`
via `CameraDirector.position_for(index, total)`.
