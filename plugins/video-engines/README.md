# plugins/video-engines

Third-party or experimental `IVideoEngine` implementations that aren't
part of the core supported set.

The reference implementation (`Wan21Adapter`) lives in
`services/video-engine-adapter` since it's the default engine. A future
custom foundation model adapter is expected to start here as an
experimental plugin and graduate into `services/video-engine-adapter`
once it's production-ready — see `docs/ARCHITECTURE.md` roadmap Phase 8.

**Status:** empty by design in Phase 0.
