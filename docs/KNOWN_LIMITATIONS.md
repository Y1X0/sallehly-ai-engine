# Known limitations: Wan2.2 TI2V-5B at Baseline v1.0

Practical reference for anyone generating video with this engine, not just developers. Based on real Kaggle T4 evidence: the 30-category robustness benchmark (`eval/reports/0026-robustness-benchmark-30-categories.md`) and the follow-up architecture prompt study (`eval/reports/0027-phase2-architecture-prompt-study.md`). Frozen config for every result below: `640x352`, `9` frames, `20` steps, `guidance_scale=5.0`, `seed=42`.

| Capability | Current status | What to do |
|---|---|---|
| Close-framed single subject (animal/object) | Excellent | No change needed. |
| Atmospheric/single-anchor scenes (horror, fantasy, sci-fi) | Excellent | No change needed. |
| Water/fire/motion phenomena | Excellent | No change needed. |
| Food/product close-ups | Excellent | No change needed. |
| Portraits/faces | Good | No change needed. |
| Landscapes with one compositional anchor | Good | No change needed. |
| Two-person, low relative motion | Good | No change needed. |
| Non-photorealistic style transfer (anime, etc.) | Good | No change needed. |
| Indoor static scenes | Good | No change needed. |
| Night/rain street scenes | Good, facades stay soft | No change needed for the wet-street subject; expect soft building facades in the background. |
| Fashion/single-object staged scenes | Good | No change needed. |
| Architecture / buildings (single, named subject) | Good, when prompted correctly | Name one concrete subject ("an isolated skyscraper", "a lone modern building") instead of an abstract style goal ("minimalist", "smooth facade"). See eval/reports/0027 Principle 1. |
| Architecture / buildings (with a foreground anchor) | Good, when composition keeps both in focus | Use anchors that share the building's depth of field (a person looking up at it, a fountain in front of it) - avoid a close foreground object (e.g. a parked car) that throws the building into background blur. See eval/reports/0027 Principle 2. |
| Architecture / buildings (camera angle) | Aerial and extreme close-up work well; street-level is unreliable | Prefer an aerial view or an extreme close-up on one facade. A street-level "looking up" framing tends to pull a dense repeated skyline back into the shot. See eval/reports/0027 Principle 3. |
| Architecture / buildings, no prompting guidance applied (default style prompts, "futuristic city skyline", "smooth facade", "minimalist") | Weak | Rewrite the prompt per the three principles above before assuming a training fix is needed. |
| Multi-entity interaction / complex relative motion (e.g. combat) | Weak | Avoid asking for two+ entities in active complex physical interaction; low-motion multi-person scenes (dialogue) work fine. |
| Diffuse wide vista with no compositional anchor (open mountains, open meadow) | Weak | Add one clear anchor (a river, a light source, a single object) to the composition. |
| Small/distant subject in a complex wide backdrop (e.g. a bird over mountains) | Weak | Frame the subject larger/closer, or drop the complex backdrop. |
| Extreme macro close-up of complex organic texture (e.g. skin, steam, ceramic glaze) | Weak | Avoid extreme close framing on complex organic textures; simple/symmetric phenomena (a droplet, geometric facades) hold up fine at close range. |

**Methodology note:** CLIP similarity is the primary quantitative signal used to build this table, but it can diverge from direct visual judgment (see `cinematic_trailers` in eval/reports/0026). Every row above was confirmed by real decoded-frame visual inspection, not CLIP scores alone.
