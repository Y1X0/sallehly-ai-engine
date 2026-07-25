from __future__ import annotations


class AutomationError(Exception):
    """Base class for every error raised by services/training/automation.
    Kept separate from training.errors.ModelUnavailableError - these
    failures are about the automation glue (a CLI missing, a job failing,
    an approval missing), never about a model not being trained yet."""


class KaggleCLINotAvailableError(AutomationError):
    """Raised when the `kaggle` CLI isn't on PATH and no runner/cli_path
    override was supplied. Mirrors dataset.metadata.FfprobeNotAvailableError."""


class KaggleAutomationError(AutomationError):
    """Raised on any non-zero exit from the `kaggle` CLI, or when its
    output can't be parsed into the shape this client expects."""


class ModalCLINotAvailableError(AutomationError):
    """Raised when the `modal` CLI isn't on PATH and no runner/cli_path
    override was supplied."""


class ModalAutomationError(AutomationError):
    """Raised on any non-zero exit from the `modal` CLI, or when its
    output can't be parsed into the shape this client expects."""


class ApprovalRequiredError(AutomationError):
    """Raised by CostGuard.authorize_paid_job() when no APPROVED
    ApprovalRecord exists for a job. This is the concrete enforcement of
    "never start a paid GPU job without approval" - every paid-tier
    dispatch path in TrainingController must pass through here first."""


class BudgetExceededError(AutomationError):
    """Raised by CostGuard.authorize_paid_job() when the job's estimated
    cost would push total spend for the current period over the
    configured monthly_budget_usd."""


class UnapprovedConfigOverrideError(AutomationError):
    """Raised by ExperimentConfigGenerator when a requested override falls
    outside the human-set allowed_ranges - the enforcement mechanism
    behind "AI can vary experiments within pre-approved ranges only"."""
