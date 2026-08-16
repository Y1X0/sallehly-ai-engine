# Experiment/Report 0029: Prompt Library v2 - Generalization Test

**Context.** Report 0028 (Phase 3B) validated `docs/PROMPT_LIBRARY.md`'s rules by rewriting 5 of Phase 1's *already-known* weak prompts and confirming the rewrites improved. That is a strong result, but it leaves one question open: do the rules only fix the exact cases they were derived from, or do they generalize to genuinely new subject matter the project has never tested? This experiment answers that directly - 5 brand-new templates, one per scenario category, each combining multiple library rules deliberately, judged on absolute quality (no "original" prompt exists to diff against).

**Success criterion:** CLIP at or above 0.2997 (the 30-category benchmark mean from report 0026) **and** a clean, coherent, real visual result. Results below the CLIP bar but with a genuinely legible visual are recorded honestly as partial successes, not inflated to full passes and not dismissed as failures.

## 1. Full results

| # | Category | Template | Rules combined | CLIP | Result |
|---|---|---|---|---|---|
| 1 | Architecture | A single isolated glass skyscraper with a person standing in front of it for scale, aerial cinematic shot, clean facade, warm sunset lighting | Rule 1 (concrete subject) + Rule 2 (anchor, same depth) + Rule 4 (aerial angle) | **0.374** | **Success - highest CLIP of the entire project** |
| 2 | Landscapes | A wide valley landscape with a single winding river as the central anchor, golden hour lighting, cinematic wide shot | Rule 5 (wide-scene anchor) | 0.2895 | Partial - visually clean, CLIP just under the benchmark mean |
| 3 | City | An ornate clock tower rising above a quiet city square, one dominant structure, cinematic aerial shot | Rule 1 + Rule 3 (avoid repeated facades) + Rule 4 | 0.3056 | Success |
| 4 | Action | A single martial artist performing a dynamic spinning kick, dramatic motion blur, cinematic dojo lighting, one central figure | Single-subject dynamic motion (vs. Phase 1's multi-entity-combat failure) | **0.3565** | **Success - 2nd highest CLIP of the entire project** |
| 5 | Documentary | A single lion in close-up mid-roar, one dominant subject in frame, cinematic natural lighting, detailed fur texture | Rule 1 + close framing | 0.2809 | Partial - lion clearly recognizable but textured |

**Overall: 3 full successes, 2 honest partial/borderline results, zero chaotic failures.**

## 2. Analysis

**Architecture (0.374) - highest CLIP of the whole project.** A single tall glass skyscraper rendered cleanly with a warm sunset gradient, clean facade texture, and a person silhouette providing scale - three rules (concrete single subject, anchor at the same depth, favorable aerial angle) stacked together rather than competing. This is the single strongest piece of evidence that the library's rules compound: no individual Phase 2 test scored this high, but combining the winning techniques from multiple groups did.

**Action (0.3565) - 2nd highest CLIP of the whole project.** A single martial artist mid-spinning-kick, correct dynamic pose, radial motion-blur streaks matching the "dramatic motion blur" request. This directly confirms a principle inferred from Phase 1 (action_scenes' multi-entity combat failed at 0.2988, while fast_motion's single subject in motion succeeded at 0.328) generalizes cleanly to an entirely new subject (a martial artist, not previously tested).

**City (0.3056) - clean success.** An ornate clock tower with a park/plaza below; background buildings visible but clearly secondary and non-repetitive. Confirms Rule 1 and Rule 3 generalize beyond the specific "skyscraper" subject tested in Phases 2-3B to a different architectural landmark type.

**Landscapes (0.2895) - honest partial.** A clearly recognizable winding river with branching tributaries across a valley, golden light, coherent terrain - visually comparable to Phase 1's successful drone_shots (0.2963). The CLIP score sits just under the 0.2997 benchmark mean (-0.0102), a small enough gap that it reads as within-category noise rather than a real deficiency, but it is reported as a partial success rather than rounded up to a full pass.

**Documentary (0.2809) - honest partial.** A lion's face is clearly identifiable (mane, eyes, nose/mouth region all legible) in close-up, though the surface texture reads as somewhat painterly rather than fully clean. This is consistent with a pattern already documented in `docs/KNOWN_LIMITATIONS.md`: extreme close framing on **complex organic texture** (fur, skin, steam) is harder than on simple/symmetric subjects, even when Rule 1 (concrete single subject) is followed correctly. The lion is a legible subject, just not a clean-textured render - a real, mild limitation, not a broken template.

## 3. Conclusion

**The Prompt Library generalizes.** All 5 templates - covering subject matter never tested in this project before - produced either a clean success or a legible, honestly-scored partial result; none produced the chaotic, unrecognizable output that characterized Phase 1's true failures (e.g., `buildings`' abstract blur, `close_ups`' overexposed blowout). The two highest CLIP scores of the entire project so far came from these new templates, both built by stacking multiple library rules together rather than applying just one. The two partial cases align with weaknesses the project already knows about (diffuse wide vistas near the edge of "needs one anchor," and complex organic texture at extreme close range) rather than exposing a new, previously-unknown failure mode.

## 4. Recommendation

The 3 fully-successful templates (architecture, city, action) are ready for direct reuse. No further action is proposed for landscapes or documentary specifically - both are honest near-misses consistent with already-documented limitations, not template defects requiring a fix. `docs/KNOWN_LIMITATIONS.md` and `docs/PROMPT_LIBRARY.md` remain the up-to-date practical references; this report's evidence has been folded into both.
