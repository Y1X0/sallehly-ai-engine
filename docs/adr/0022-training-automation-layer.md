# ADR 0022: Training Automation Layer - Kaggle/Modal integration, GitHub Actions orchestration, AI training controller, cost protection

**Status:** Accepted

## Context

The "Sallehly Autonomous Training Factory" architecture report (zero/
near-zero-cost track, delivered alongside this ADR) designed the
automation layer that sits underneath Phase 9 Preparation
(`services/training`, ADR 0021) and the Wan 2.2 fine-tuning blueprint:
not *what* to train, but what pushes the buttons, and what it costs to
let it. This ADR is that design turned into real code. Per explicit
instruction: no GPU is rented, no model is downloaded, and no training
is executed anywhere in this change - only the automation infrastructure
around Kaggle, Modal, GitHub Actions, and cost protection.

## Decisions

### 1. `services/training/src/training/automation/`: a sixth submodule, same flattening convention

`kaggle_client.py`, `modal_client.py`, `approval.py`, `budget.py`,
`controller.py`, `errors.py` - flattened into `automation/__init__.py`
and then into the top-level `training/__init__.py`, identical to how
`dataset/`, `registry/`, and `evaluation/` were added in ADR 0021. This
package depends on nothing beyond the Python standard library
(`subprocess`, `json`, `pathlib`) plus `training.config.TrainingConfig` -
no new third-party dependency was added to `services/training`'s
`pyproject.toml`.

### 2. Kaggle and Modal are wrapped as real CLI subprocess clients with an injectable `runner`

`KaggleClient` and `ModalJobLauncher` both shell out to the real
`kaggle`/`modal` CLIs (`kaggle datasets ...`, `kaggle kernels ...`,
`modal run --detach`, `modal app logs`/`stop`) rather than reimplementing
either provider's REST API - both CLIs are the officially documented
integration surface. A `runner: Callable[[list[str]],
subprocess.CompletedProcess]` can be injected in place of
`subprocess.run`, exactly the pattern `dataset/metadata.py` already uses
for `ffprobe` and `RunPodProvider` uses for `httpx.Client` - so
`tests/test_training_automation.py` never touches a real network, a
real CLI binary, or real credentials, while the production code path is
the real thing.

### 3. "Automatic shutdown after completion" is Modal's own guarantee; the launcher only adds a wall-clock safety net

Modal's serverless billing model already scales a function to zero the
instant it returns - `ModalJobLauncher` does not reimplement that. What
it adds is `enforce_wall_clock_ceiling()`: a caller-supplied
`is_complete()` check polled against an injectable clock, which calls
`modal app stop` if `ModalJobConfig.max_wall_clock_sec` is exceeded. This
is a belt-and-suspenders ceiling for a hung job, not the primary
shutdown mechanism.

### 4. Cost protection is one choke point (`CostGuard`), not a convention

Every paid-tier dispatch path must call
`CostGuard.authorize_paid_job(job_id, estimated_cost_usd)` first. It
raises `ApprovalRequiredError` unless an `ApprovalRecord` for that exact
`job_id` is `APPROVED` (and the estimate is within the approval's own
`max_cost_usd` ceiling - a human approving a $10 run cannot be
reinterpreted as approving a $200 one), and raises `BudgetExceededError`
if the estimate would push the current month's recorded spend
(`IUsageLedger`, keyed by `UsageRecord.current_period_key()`) over
`monthly_budget_usd`. `TrainingController.plan_experiment()` calls this
before a `PAID_GPU`-tier `JobRecord` is ever created - there is no code
path that skips it.

### 5. The GitHub `paid-gpu-approval` Environment's required-reviewers rule IS the human approval gate, not a UI convention layered on top

`.github/workflows/training-phase3-paid-gpu-gate.yml` sets `environment:
paid-gpu-approval` on its only job. GitHub itself blocks that job from
starting until a configured reviewer approves the pending deployment -
this is enforced by GitHub, not by this repository's code. Only once
that gate has passed does `authorize_paid_job.py` run at all, and it
records exactly what the reviewer authorized (`--max-cost-usd` from the
workflow's own input) as the `ApprovalRecord` `CostGuard` then re-checks.
Two independent systems (GitHub's environment protection, this
package's `CostGuard`) both have to agree before a dollar is spent.

### 6. `ExperimentConfigGenerator` only allows overriding pre-approved top-level scalar fields, within pre-approved ranges

`generate_variant(base, overrides)` checks every override key against a
human-authored `allowed_ranges` map (checked in as
`services/training/automation/allowed_ranges.example.json`) and raises
`UnapprovedConfigOverrideError` for any field not listed or any value
outside its range - this is the concrete enforcement of "AI can vary
experiments within pre-approved ranges only" from the architecture
report. Changing `lora` (rank/alpha/target modules) or `strategy` is
deliberately not overridable this way at all; those remain config
authored by a human, matching the fine-tuning blueprint's (ADR-adjacent
report) framing of LoRA-rank-tier changes as a strategic call.

### 7. Three GitHub Actions workflows map exactly onto the architecture report's three phases

`training-phase1-dataset-validation.yml` (CPU only, push/PR triggered,
$0, no approval), `training-phase2-free-gpu-experiment.yml` (scheduled +
manual dispatch, targets Kaggle/Modal free tiers, $0, no approval),
`training-phase3-paid-gpu-gate.yml` (manual dispatch only, gated by the
`paid-gpu-approval` Environment, the only workflow that can plan a
`PAID_GPU` job). No workflow can reach a paid dispatch without going
through Phase 3's gate - Phase 1/2 workflows never construct a
`CostGuard` at all.

### 8. `run_experiment.py --dispatch` fails fast rather than pretending to work

The CLI script backing all three workflows (`services/training/scripts/
run_experiment.py`) defaults to `--plan-only` (config generation + job
tracking + reporting - the real, tested part of the loop this change
delivers) and requires an explicit `--dispatch` flag to attempt a real
Kaggle/Modal call. `--dispatch` currently always fails with a clear
message: real dispatch needs a training entrypoint script (the
`code_file` a Kaggle kernel runs, or the Modal `app_entrypoint` a `modal
run` invokes) that does not exist yet, because writing the actual Wan
2.2 LoRA training script is Phase 9 *execution* - explicitly out of
scope for "automation infrastructure only, no training execution."

## Consequences

- Every workflow, script, and client added here is exercised for real in
  this repository's own CI (`uv run pytest tests/test_training_
  automation.py`, and both scripts were run by hand end-to-end against
  fake CLI runners and a real filesystem approval/budget store during
  development) - nothing is a stub pretending to be finished.
- Real Kaggle/Modal credentials (`KAGGLE_USERNAME`/`KAGGLE_KEY`,
  `MODAL_TOKEN_ID`/`MODAL_TOKEN_SECRET`) and a `paid-gpu-approval`
  Environment with reviewers configured are both required before Phase
  2/3 workflows do anything beyond planning - neither exists in this
  repository yet, by design (no GPU rental happened as part of this
  work).
- The remaining gap before any workflow can reach a real trained
  checkpoint is exactly one thing: a training entrypoint script
  (Kaggle kernel `code_file` / Modal `app_entrypoint`) implementing the
  Wan 2.2 LoRA fine-tuning blueprint against `services/training`'s
  existing `ITrainer`/`ICheckpointStore`/`IModelRegistry` interfaces -
  that is real Phase 9 execution and a separate, explicit next step.
