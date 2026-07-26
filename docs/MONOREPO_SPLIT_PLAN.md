# Repository Independence: Sallehly App / Sallehly AI Engine

**Status:** Corrected finding, superseding an earlier version of this document. No files have been moved.

**Correction note:** an earlier version of this document assumed "Sallehly App" referred to `apps/api` +
`apps/web-dashboard` + the creative-direction pipeline living *inside this same repository*, and proposed splitting
this repo in two. That assumption was wrong and has been retracted in full — see §1. This version replaces it with
the actual finding.

---

## 1. What "Sallehly App" and "Sallehly AI Engine" actually are

**Sallehly App** is `github.com/Y1X0/sallehly_app` — a real, independently-developed **Flutter mobile app** with its
own **Firebase** backend. Verified directly, not assumed:

- `pubspec.yaml`/`pubspec.lock`, `android/`, `ios/`, `linux/`, `macos/`, `windows/`, `web/`, `.metadata` — standard
  Flutter project scaffolding.
- `lib/firebase_options.dart` — a real Firebase project wired in.
- `lib/features/`, `lib/providers/`, `lib/routes/`, `lib/config/`, `lib/core/`, `lib/models/` — a genuine,
  structured Flutter app (not a stub), with its own routing, state management, and data models.
- `codemagic.yaml` — Flutter-specific mobile CI/CD (Codemagic, not GitHub Actions).
- Zero references anywhere in that repository's top-level tree or `lib/` structure to video generation, Wan2.x,
  render pipelines, or anything from this AI engine's domain.

**Sallehly AI Engine** is this repository, `sallehly-ai-video-engine`, in its **entirety** — Python (`apps/api`,
every `services/*`, every `packages/*`), TypeScript (`apps/web-dashboard`), and everything else in this tree. There
is no "App" content living inside this repository to extract. `apps/api` and `apps/web-dashboard` are the AI
Engine's *own* API and dashboard — its own product surface — not a second product sharing this codebase.

This was, in fact, decided and recorded on day one of this project and never violated:

> `docs/DECISIONS.md`, row 7: "Repository: `sallehly-ai-video-engine`, fully separate from `sallehly_app` |
> Independent product, not a feature of the existing Flutter app"

The two products have been architecturally independent since before any AI Engine code existed. The task this
document now answers is not "how do we split this repo" — it's "confirm, with evidence, that the independence
already holds, and flag anything that would put it at risk."

---

## 2. Coupling audit — both directions, verified

### 2.1 Does `sallehly-ai-video-engine` reference `sallehly_app`?

```
grep -rl "sallehly_app" --include="*.py" --include="*.ts" --include="*.tsx" \
     --include="*.md" --include="*.yaml" --include="*.yml" --include="*.toml" .
```

Two hits, both **documentation, stating the separation, not violating it**:

- `docs/DECISIONS.md` row 7 (quoted above).
- `docs/ARCHITECTURE.md`: "...from the `sallehly_app` Flutter product — the video platform is an [independent
  product]".

No import, no URL, no config key, no build dependency, no CI reference. Zero code-level coupling in either
direction.

### 2.2 Does `sallehly_app` reference this AI Engine?

Checked directly against the live repository: top-level tree, `README.md` (generic, unmodified Flutter
boilerplate — "A new Flutter project"), and `lib/` structure. Nothing references video generation, this engine's
domain, or this repository. The app's own backend is Firebase, not this engine's Postgres/Redis/Temporal/S3 stack —
there is no shared infrastructure to find, because none exists.

### 2.3 Namespace collisions

None possible in principle — different languages (Dart vs. Python/TypeScript), different package ecosystems (pub.dev
vs. PyPI/uv workspace vs. npm), different repositories, different CI systems (Codemagic vs. GitHub Actions). There is
no shared registry either could accidentally collide in.

### 2.4 Circular dependencies

None — there has never been an edge in either direction to be circular.

---

## 3. Conclusion

The independence the request asks for already exists, verified in both directions rather than assumed. Every
"finding" in the retracted earlier version of this document (the `apps/api` ↔ `video_engine_adapter` coupling, the
`video_engine_adapter` ↔ `config_sdk` coupling, the boundary-spanning tests) is real, but describes an *internal*
seam inside the AI Engine's own `IVideoEngine`/`IComputeProvider` abstraction (ADR 0001/0002) — the deliberate
boundary between this engine's interface and its concrete Wan2.1/Sallehly adapters. It has nothing to do with
`sallehly_app`, and does not need to be resolved to satisfy this request. That earlier analysis is not deleted from
git history, just superseded by this corrected version — it may still be useful later if there's ever a reason to
extract `services/video-engine-adapter`/`services/training` into their own repository separate from the rest of
this engine, which is a different, unrelated question from the one asked here.

## 4. What, if anything, is left to do

Nothing code-level — the independence already holds. Two small, optional items, worth naming rather than silently
doing:

1. **This repository has no git remote configured yet** (verified: `git remote -v` returns nothing). It exists only
   locally in this session. If you want `sallehly-ai-video-engine` to be a real, independent second repository
   alongside `sallehly_app` on GitHub — rather than just a local checkout — it needs to be pushed to a new remote
   (e.g. `sallehly-ai-engine`, distinct from both its current local directory name and from `sallehly_app`). I
   haven't done this — creating a new repository and pushing to it is exactly the kind of action worth confirming
   with you first, not assuming.
2. **`.env.example`, `docker-compose.yml`, and this repo's docs already describe this engine as self-contained** —
   no changes needed there; they never referenced `sallehly_app` as a dependency to begin with.
