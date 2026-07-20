# services/training

## Training (future foundation model track)

**Responsibility:** long-term, parallel R&D track — not part of the
production request path. Will eventually own the dataset pipeline,
fine-tuning/LoRA training runs, and an evaluation harness for the custom
video foundation model that is meant to eventually replace Wan2.1 (see
`docs/ARCHITECTURE.md` roadmap Phase 8 and
`docs/adr/0001-director-engine-separation.md`).

**Status:** placeholder only. No scaffolding yet — intentionally, since
none of Phase 0-7 depends on this existing. When it starts, its eventual
output is a new `IVideoEngine` implementation living in
`services/video-engine-adapter/src/video_engine_adapter/adapters/`,
following the exact same contract `Wan21Adapter` implements today.
