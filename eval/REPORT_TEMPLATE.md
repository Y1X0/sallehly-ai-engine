# Quality Iteration Report Template

Copy this into `eval/reports/NNNN-short-slug.md` for every real Kaggle
GPU generation used to evaluate or change quality. Never fill in scores
or verdicts without a real video + real `eval/quality_metrics.py`
output as evidence - no simulated/estimated numbers.

---

## Iteration NNNN: <short title>

**Kaggle run:** <workflow run URL> (job id, commit sha)
**Prompt:** `<exact prompt used>`
**Params:** resolution, num_frames, fps, sampling_steps, guidance_scale, seed

### 1. What was tested
<one or two sentences>

### 2. What failed / what was observed
<concrete, specific observations - not "quality is bad", but e.g.
"every sampled frame's avg RGB stddev is 9.2, well under the 20.0
flat-frame threshold">

### 3. Root cause
<the *mechanism*, with a citation to code/logs/docs - never a guess.
If unconfirmed, say "unconfirmed - next experiment isolates this">

### 4. Evidence
- `eval/quality_metrics.py` output (paste the JSON or link the report artifact)
- Kaggle job log excerpt if relevant (timing, error text)
- Any frame screenshots

### 5. What was changed
<the ONE variable changed this iteration - never more than one>

### 6. Before vs after comparison
| Metric | Before | After |
|---|---|---|
| avg_stddev | | |
| flat_frame_suspected | | |
| run duration (sec) | | |
| (any category-specific note) | | |

### 7. Benchmark scores (this prompt only, /10 each)
| Dimension | Score | Notes |
|---|---|---|
| Prompt understanding | /10 | |
| Object correctness | /10 | |
| Scene correctness | /10 | |
| Cinematic quality | /10 | |
| Motion quality | /10 | |
| Lighting | /10 | |
| Camera movement | /10 | |
| Realism | /10 | |
| Consistency | /10 | |
| Flickering (10 = none) | /10 | |
| Temporal coherence | /10 | |
| Subject identity | /10 | |
| Composition | /10 | |
| Color grading | /10 | |
| Artifacts (10 = none) | /10 | |
| **Overall** | **/10** | |

### 8. Remaining weaknesses
<bulleted list>

### 9. Next experiment
<the single next variable to test, and why - links back to §8>
