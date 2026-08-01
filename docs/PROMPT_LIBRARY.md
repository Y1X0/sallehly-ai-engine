# Prompt Library v1 - Wan2.2 TI2V-5B

Not a model change. This is a reusable set of prompt-writing rules for anyone
generating video with this engine, built directly on real benchmark evidence:
`eval/reports/0026-robustness-benchmark-30-categories.md` (30-category
Capability Map) and `eval/reports/0027-phase2-architecture-prompt-study.md`
(17-run causal study proving the architecture weakness is a prompting issue,
not a model ceiling - Case A). Every rule below cites the specific before/after
CLIP scores that produced it. Validation of this library against 5 of Phase 1's
weakest categories is tracked in `eval/reports/0028-phase3b-prompt-library-validation.md`.

Frozen config assumed throughout: `640x352`, `9` frames, `20` steps,
`guidance_scale=5.0`, `seed=42`.

## 1) Single Subject Architecture

**Use when:** you want one building to be the clear hero of the shot.

❌ Weak - abstract design concepts, no concrete visual object:
> futuristic minimalist architecture, clean lines, modern city

(`eval/reports/0027` B.3: "minimalist office building facade, clean lines" → **0.2424**, the lowest CLIP of the entire project - blocky, glitchy mosaic, no coherent building.)

✅ Strong - one named, concrete subject:
> a single isolated modern skyscraper, one building as the main subject, clean glass facade, cinematic aerial shot

(`eval/reports/0027` A.1: "an isolated skyscraper standing against a clear sky" → **0.3156**, clean tapered silhouette.)

**Rule:** the model responds to a visual entity it can render ("a tower," "a building"), not a design critique ("minimalist," "clean lines"). Name the object; don't describe the aesthetic philosophy behind it.

## 2) Architecture + Human-Scale Anchor

**Use when:** you need a sense of scale, or want a person/object in the frame with the building.

Best anchors (share the building's depth of field): a person looking up at it, a fountain in front of it. Avoid a close foreground object with a shallow depth of field (a parked car) - it renders perfectly but pushes the building into background blur.

✅ Strong:
> a single glass tower with a person standing in front of it, showing the massive scale, cinematic lighting

(`eval/reports/0027` C.2: "a person standing before a glass tower" → **0.3129**, both person and tower clearly rendered. C.3's fountain-in-front-of-city-hall scored **0.3148**, similarly excellent.)

❌ Weak counter-example:
> a red sports car parked in front of a glass skyscraper

(`eval/reports/0027` C.1 → **0.2718** - the car rendered perfectly, but the skyscraper dissolved into soft bokeh blur.)

**Rule:** an anchor helps only when it shares the building's plane/depth of field. A foreground object that implies shallow depth of field pulls the model's attention away from the architecture rather than showcasing it.

## 3) Avoid Repeated Facades

**Use when:** describing a building's surface or a city skyline.

❌ Weak - invites the repeated-geometry failure mode directly:
> hundreds of windows, dense city towers, complex skyline

✅ Strong:
> smooth facade, simple silhouette, one dominant structure

(`eval/reports/0026` found repeated fine-grained geometry + deep perspective, combined, to be the single most consistent weak cluster across the whole 30-category benchmark - buildings 0.2915, city 0.2813, both below the 0.2997 mean.)

**Rule:** many small repeated elements (windows, vehicles, pedestrians) held in deep perspective is the core failure mode. Reduce the count of repeated elements in the prompt itself rather than asking for a vague "minimalist" style (see Rule 1 - style words alone don't work).

## 4) Camera Selection

**Use when:** choosing how to frame a building shot. Ranked by confidence, from `eval/reports/0027` Group D:

1. 🥇 **Aerial** - `0.3331`, clean tower with distant background, no competing nearby architecture.
2. 🥈 **Extreme close-up** (on one facade) - `0.3053`, highest sharpness of the whole study; the repeated grid becomes a simple symmetric texture at this scale.
3. 🥉 **Oblique angle** - `0.2938`, borderline/painterly but usable.
4. ❌ **Street level** (for complex/urban scenes) - `0.2723`, the model tends not to follow this instruction faithfully and reintroduces a dense repeated skyline.

**Rule:** for a single building as the subject, prefer aerial or an extreme close-up on one facade. Reserve street-level framing for scenes where a busy street IS the intended subject (Phase 1's `night_scenes`/`rain` succeeded with street-level framing when the wet street, not the architecture, was the hero).

## 5) Wide Scene Rule

**Use when:** the scene is a wide vista (landscape, cityscape, skyline) with no single obvious subject.

❌ Weak - diffuse, no compositional anchor:
> a huge futuristic city

✅ Strong - one clear anchor pulls the composition together:
> a huge futuristic city with one central tower illuminated at sunset

(`eval/reports/0026` found this pattern outside architecture too: `mountains` (0.2564) and `outdoor` (0.2579) both failed as diffuse wide vistas with no anchor, while `nature` (0.3081, forest+river+light) and `drone_shots` (0.2963, winding river) succeeded as wide shots specifically because they had one strong compositional anchor.)

**Rule:** any wide/diffuse scene - architectural or natural - needs one leading element (a tower, a river, a light source) for the model to organize the composition around. A wide shot with no anchor tends to collapse into an abstract, chaotic texture regardless of subject matter.

---

These 5 rules are prompt-only and require no changes to the frozen Baseline v1.0
config. See `eval/reports/0028-phase3b-prompt-library-validation.md` for a
direct test of whether rewriting failing prompts per this library closes the
gap against the originals.
