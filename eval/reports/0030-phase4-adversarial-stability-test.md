# Experiment/Report 0030: Phase 4 - Adversarial Prompt Test + Stability

**Context.** Reports 0027-0029 showed the Prompt Library (`docs/PROMPT_LIBRARY.md`) fixes real, previously-diagnosed prompting mistakes and generalizes to new subjects. That left one open question: is the library strong enough to hold up under *genuinely hard, adversarial* prompts - the kind a real user might actually write - or does even a well-formed prompt hit a real capability ceiling? This phase also introduces a new metric, **Prompt Control Stability**: does a prompt's requested composition (entity count, framing, structural integrity) survive across different random seeds, or does it depend on getting lucky with one seed?

**Methodology correction (made before any run was dispatched).** The original plan was to repeat each adversarial prompt 3x to test stability. Phase 2's Control measurements (report 0027) proved the pipeline is fully deterministic - identical prompt + identical seed produces a byte-identical video every time. Repeating a prompt at a fixed seed would therefore have produced 3 identical, uninformative results. The seed was varied per repeat instead (**42, 123, 777**) - the only way to actually test whether a composition holds up across different random draws.

**Success criterion per test:** (a) CLIP quality per seed, judged against the 0.2997 benchmark mean (report 0026), **and** (b) a stability verdict - does the requested subject/entity-count/composition survive across all 3 seeds, or does it visibly collapse or vary?

**Decision tree (locked before dispatch):**
- 70-80%+ of tests pass on both quality and stability → Prompt Control Layer is strong, LoRA is not a priority.
- Failures only under deliberate overload (the composition-overload test) → add more Prompt Library rules, no LoRA.
- Failures even on individually-reasonable adversarial prompts (not just the extreme overload case) → open the LoRA/fine-tuning question for real.

**Scope note.** The plan called for 5 tests × 3 seeds = 15 runs. After Test A, B, and C completed (10 of 15 runs), the user reviewed the cumulative evidence across Phases 1-4 and made an explicit decision to stop further prompt-only testing (Tests D and E were not run) and pivot the project to dataset collection and fine-tuning planning. This is a deliberate scope cut based on sufficient evidence, not an error or incomplete work - the results below already answer the phase's core question decisively.

## 1. Full results (10 of 15 planned runs)

| Test | Prompt | Seed | CLIP | Visual verdict |
|---|---|---|---|---|
| A - multi-entity combat | Three martial artists fighting, one performing a jumping kick, one blocking, one falling, dynamic camera, cinematic | 42 | 0.2931 | Only 2 of 3 fighters clearly distinguishable. |
| A | (same) | 123 | 0.2955 | Again only 2 of 3 fighters. |
| A | (same) | 777 | 0.2874 | Again exactly 2 fighters. |
| B - dense architecture | A futuristic city with skyscrapers, traffic, pedestrians, signs, and reflections, cinematic wide shot | 42 | 0.3204 | Clean - skyscrapers in symmetric perspective, reflecting pool anchor, pedestrians visible. |
| B | (same) | 123 | 0.2872 | Weaker - blocky/painterly facades, repeated window-stripe texture, no anchor, chaotic sky smear. |
| B | (same) | 777 | 0.326 | Clean - symmetric street canyon, central spire anchor, neon lighting, pedestrians legible. |
| C - small/distant subject | A wolf standing in a distant mountain valley, wide cinematic shot | 42 | 0.2665 | Wolf clearly rendered but large/foreground, not distant; background glitch artifacting. |
| C | (same) | 123 | 0.2487 | Same near/large framing failure; worse background chaos (lowest CLIP of Phase 4). |
| C | (same) | 777 | 0.3102 | Cleanest wolf render of the 3, but still large/foreground, not distant; milder background glitch. |
| D - composition overload | *(not run - phase stopped by user decision)* | - | - | - |
| E - motion + complexity | *(not run - phase stopped by user decision)* | - | - | - |

## 2. Per-test stability verdicts

**Test A - STABLE BUT CAPPED.** All 3 seeds (CLIP 0.2874-0.2955, all below the 0.2997 benchmark mean) rendered exactly 2 of the 3 requested fighters, never 3. This is a real, reproducible ceiling on entity count in active combat scenes - the model consistently commits to 2 clear figures rather than attempting a third, regardless of random seed. This confirms and hardens Phase 1's `action_scenes` finding (2 fighters requested, 1 rendered) into a seed-independent result.

**Test B - MOSTLY STABLE, ONE CRACK.** Seeds 42 (0.3204) and 777 (0.326) both produced clean, coherent cityscapes with a strong central anchor and legible pedestrians, both above the benchmark mean. Seed 123 (0.2872) was a real outlier - below the mean, blocky facades, repeated window texture, no anchor. 2 of 3 seeds pass cleanly; this prompt's deliberately overloaded element list (skyscrapers + traffic + pedestrians + signs + reflections) occasionally tips into the known repeated-facade failure mode on an unlucky seed, but is not a hard ceiling.

**Test C - FRAMING INSTRUCTION FAILS CONSISTENTLY.** All 3 seeds (CLIP 0.2487-0.3102, quality itself varied a lot) rendered the wolf large/foreground, never actually "distant" as the prompt explicitly requested. This is a different kind of failure from Test A's entity cap: it is not an occasional quality crack (Test B) or a count ceiling (Test A) - it is the model consistently declining to honor a specific spatial-framing instruction regardless of seed, while the wide mountain background also showed glitch artifacting in 2 of 3 seeds.

## 3. Applying the decision tree

The evidence from the 10 completed runs is unambiguous against the locked decision tree:

- Test A fails **on every seed**, on an individually reasonable prompt (a 3-person fight is not an extreme overload case).
- Test C fails **on every seed**, on an individually reasonable prompt (a wolf in a distant valley is a plain, common shot request).
- Only Test B shows the "fails occasionally under a loaded-but-still-single prompt" pattern, and even there 2 of 3 seeds are genuinely clean.

This matches the decision tree's third branch directly: **failures even on individually-reasonable adversarial prompts, not just the deliberate overload case (Test D, not run) → the LoRA/fine-tuning question is open for real.** Both Test A (entity-count ceiling) and Test C (framing-instruction ceiling) are real, seed-independent limitations that no amount of prompt rewriting demonstrated in Phases 2-3B was able to touch - they are structurally different from the architecture-prompting weakness that Phase 2 proved was fixable with prompting alone.

## 4. Conclusion

Phase 4 completes the diagnostic arc that began in Phase 1: the project now has strong, seed-verified evidence that **some real weaknesses are prompting problems (fixed in Phases 2-3B) and some are real capability ceilings of the current model weights** (multi-entity counts beyond 2, and specific spatial-framing instructions like "distant"/"small subject"). Prompting alone cannot close these remaining gaps. This is the evidence base the project needed before considering any change to the model's weights, and the reason the project is now moving to dataset collection and fine-tuning planning rather than further prompt studies.

## 5. What was intentionally not run

Test D (composition overload: castle + river + people + birds + fog) and Test E (motion + complexity: racing cars in rain with neon) were designed to probe extreme overload and combined motion/complexity respectively. They were not run because the decision-tree question they were meant to help answer - "is this only a problem under deliberate overload, or does it show up on reasonable prompts too?" - was already answered decisively by Tests A and C, both of which failed consistently on individually-reasonable prompts. Running D/E would likely have added more overload-failure data points without changing the resulting decision.
