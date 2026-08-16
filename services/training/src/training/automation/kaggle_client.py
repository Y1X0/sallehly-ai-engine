from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from .errors import KaggleAutomationError, KaggleCLINotAvailableError

Runner = Callable[[list[str]], subprocess.CompletedProcess]


class KaggleKernelStatus(str, Enum):
    """Mirrors the status strings the real `kaggle kernels status <ref>`
    CLI command reports (lowercased in its output: "queued", "running",
    "complete", "error", "cancelAcknowledged"). QUEUED/RUNNING are
    non-terminal; the rest are terminal states poll_kernel_until_terminal
    stops on."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in (KaggleKernelStatus.COMPLETE, KaggleKernelStatus.ERROR, KaggleKernelStatus.CANCELLED)


@dataclass(frozen=True)
class KaggleDatasetRef:
    """A Kaggle dataset identifier ("owner/dataset-slug")."""

    owner_slug: str
    dataset_slug: str

    @property
    def full_ref(self) -> str:
        return f"{self.owner_slug}/{self.dataset_slug}"


@dataclass(frozen=True)
class KaggleKernelRef:
    """A Kaggle kernel (notebook/script) identifier ("owner/kernel-slug")."""

    owner_slug: str
    kernel_slug: str

    @property
    def full_ref(self) -> str:
        return f"{self.owner_slug}/{self.kernel_slug}"


@dataclass
class KernelPushConfig:
    """Everything needed to write a real kaggle-api `kernel-metadata.json`
    and push a training/experiment script as a Kaggle kernel. `enable_gpu`
    is what actually requests a free T4x2/P100 for the run; `is_private`
    defaults True since experiment code/datasets are not meant to be
    published. See https://github.com/Kaggle/kaggle-api's kernel push
    docs for the exact metadata schema this mirrors."""

    kernel_ref: KaggleKernelRef
    title: str
    code_file: str
    dataset_sources: tuple[KaggleDatasetRef, ...] = ()
    language: str = "python"
    kernel_type: str = "script"
    is_private: bool = True
    enable_gpu: bool = True
    enable_internet: bool = True
    # Leaving this unset lets Kaggle pick either accelerator for a free
    # GPU session - real runs showed it can hand out an older Pascal
    # P100, whose compute capability recent PyTorch wheels no longer ship
    # compiled kernels for at all (a real "CUDA error: no kernel image is
    # available for execution on the device", not specific to any one
    # dtype - confirmed by hand: it persisted identically after switching
    # bf16 to fp16). "NvidiaTeslaT4" / "NvidiaTeslaP100" (the exact
    # strings kagglesdk's own machine_shape field documents) let a caller
    # pin a specific accelerator instead of leaving it to chance.
    machine_shape: str | None = None

    def validate(self) -> None:
        if not self.title.strip():
            raise ValueError("KernelPushConfig.title must not be empty")
        # Kaggle's real kernel-push API enforces 5-50 chars and derives the
        # kernel's actual slug from this title, not from `id` - a title
        # outside this bound either gets a bare "400 Client Error" (too
        # long, no field-level message) or silently resolves to a
        # different slug than `id` (confirmed live both ways - see
        # dispatch_via_kaggle's _kaggle_kernel_title docstring).
        if not (5 <= len(self.title) <= 50):
            raise ValueError(
                f"KernelPushConfig.title must be 5-50 chars (Kaggle's real bound), got "
                f"{len(self.title)}: {self.title!r}"
            )
        if not self.code_file.strip():
            raise ValueError("KernelPushConfig.code_file must not be empty")
        if self.language not in ("python", "r"):
            raise ValueError(f"Unsupported language: {self.language!r}")
        if self.kernel_type not in ("script", "notebook"):
            raise ValueError(f"Unsupported kernel_type: {self.kernel_type!r}")

    def to_kernel_metadata_dict(self) -> dict:
        metadata = {
            "id": self.kernel_ref.full_ref,
            "title": self.title,
            "code_file": self.code_file,
            "language": self.language,
            "kernel_type": self.kernel_type,
            "is_private": self.is_private,
            "enable_gpu": self.enable_gpu,
            "enable_internet": self.enable_internet,
            "dataset_sources": [ref.full_ref for ref in self.dataset_sources],
            "competition_sources": [],
            "kernel_sources": [],
        }
        if self.machine_shape:
            metadata["machine_shape"] = self.machine_shape
        return metadata


@dataclass
class DatasetMetadata:
    """Minimal fields required by kaggle-api's `dataset-metadata.json`
    for `kaggle datasets create`/`kaggle datasets version`."""

    dataset_ref: KaggleDatasetRef
    title: str
    license_name: str = "other"
    subtitle: str = ""

    def validate(self) -> None:
        # Kaggle's real `datasets create` API enforces a 6-50 char bound on
        # title - found live (infra/kaggle/diagnose_dataset_attach.py's own
        # first real run): "The dataset title must be between 6 and 50
        # characters" for a 54-char diagnostic title. Never actually hit by
        # dispatch_via_kaggle()'s production titles (~27-46 chars), but
        # nothing previously checked it, so a longer job_id/dataset_slug in
        # the future would fail with a real but easily-preventable error.
        if not (6 <= len(self.title) <= 50):
            raise ValueError(
                f"DatasetMetadata.title must be 6-50 chars (Kaggle's real bound), got "
                f"{len(self.title)}: {self.title!r}"
            )
        # Same real bound dispatch_via_kaggle() already worked around by
        # hand (see its own subtitle comment) - confirmed a second,
        # independent time by diagnose_dataset_attach.py's own second real
        # run: "Subtitle length must be between 20 and 80 characters".
        # Only checked when non-empty - subtitle is optional and no real
        # evidence exists for how Kaggle treats an empty one.
        if self.subtitle and not (20 <= len(self.subtitle) <= 80):
            raise ValueError(
                f"DatasetMetadata.subtitle must be 20-80 chars when set (Kaggle's real bound), got "
                f"{len(self.subtitle)}: {self.subtitle!r}"
            )

    def to_dataset_metadata_dict(self) -> dict:
        return {
            "id": self.dataset_ref.full_ref,
            "title": self.title,
            "subtitle": self.subtitle,
            "licenses": [{"name": self.license_name}],
        }


@dataclass
class KaggleJobResult:
    """What poll_kernel_until_terminal() hands back - the terminal status
    plus wall-clock elapsed, so a caller can log/report without a second
    status call."""

    kernel_ref: KaggleKernelRef
    status: KaggleKernelStatus
    elapsed_sec: float
    raw_status_output: str = ""


_STATUS_PATTERN = re.compile(r'"([A-Za-z_.]+)"')


def _default_binary_path() -> str:
    path = shutil.which("kaggle")
    if path is None:
        raise KaggleCLINotAvailableError(
            "The `kaggle` CLI is not installed or not on PATH. Install with "
            "`pip install kaggle` and configure ~/.kaggle/kaggle.json - see docs/DEV_SETUP.md."
        )
    return path


class KaggleClient:
    """Thin, real wrapper around the official `kaggle` CLI for dataset
    upload/download and kernel push/status/output - the mechanics behind
    Phase 2's "free GPU, automatable" path from the training-factory
    architecture report. No network call is made by this class in this
    codebase's own test suite: a `runner` callable can be injected to
    replace `subprocess.run` entirely (see tests/test_training_automation.py),
    exactly the pattern dataset/metadata.py uses for ffprobe and
    video_engine_adapter's RunPodProvider uses for httpx.

    This client never decides *whether* to run a job - that decision
    (and any paid-tier approval gate) belongs to TrainingController /
    CostGuard. This class only ever talks to Kaggle's free-tier surface.
    """

    def __init__(
        self,
        *,
        runner: Runner | None = None,
        cli_path: str | None = None,
    ) -> None:
        if runner is not None:
            self._runner: Runner = runner
            self._binary = cli_path or "kaggle"
        else:
            self._binary = cli_path or _default_binary_path()
            # Plain `subprocess.run(args)` leaves .stdout as None (output
            # goes straight to this process's inherited stdout instead) -
            # confirmed by a real Kaggle run (30277585931): get_kernel_status
            # printed the real "... has status ..." line straight to the
            # job log, then crashed parsing it because result.stdout was
            # None. Every test injects its own runner with stdout already
            # set, so this default path was never actually exercised until
            # this real integration run surfaced it.
            self._runner = lambda args: subprocess.run(args, capture_output=True, text=True)

    def upload_dataset(
        self,
        local_dir: Path,
        metadata: DatasetMetadata,
        *,
        version_notes: str = "Automated dataset update",
        is_new: bool = False,
    ) -> str:
        metadata.validate()
        metadata_path = local_dir / "dataset-metadata.json"
        metadata_path.write_text(json.dumps(metadata.to_dataset_metadata_dict(), indent=2))

        if is_new:
            args = [self._binary, "datasets", "create", "-p", str(local_dir), "--dir-mode", "zip"]
        else:
            args = [
                self._binary, "datasets", "version",
                "-p", str(local_dir), "-m", version_notes, "--dir-mode", "zip",
            ]
        return self._run(args).stdout

    def get_dataset_status(self, dataset_ref: KaggleDatasetRef) -> str:
        """Real `kaggle datasets status <ref>` - Kaggle processes a freshly
        created dataset asynchronously (its own `datasets create` output
        says "Your private Dataset is being created..."); pushing a kernel
        that references it before this reaches "ready" makes Kaggle silently
        drop it from the kernel's dataset_sources (only a CLI warning, no
        error) - confirmed by hand, run 30278022296's kernel then failed
        with "No dataset mounted under /kaggle/input". Returns the raw
        lowercase status string (e.g. "ready", "blobs_received", "failed").
        """
        args = [self._binary, "datasets", "status", dataset_ref.full_ref]
        return self._run(args).stdout.strip()

    def poll_dataset_until_ready(
        self,
        dataset_ref: KaggleDatasetRef,
        *,
        poll_interval_sec: float = 5.0,
        timeout_sec: float = 180.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> str:
        """Blocks until `get_dataset_status` reports "ready" or
        `timeout_sec` elapses - see that method's own docstring for why a
        freshly created dataset must reach this state before a kernel
        referencing it is pushed. Confirmed live a second time (run
        31707456042): the push warned "not valid dataset sources" and
        silently dropped the input dataset, so the kernel had nothing
        mounted under /kaggle/input at all."""
        start = clock()
        last_status = ""
        while True:
            try:
                last_status = self.get_dataset_status(dataset_ref).strip().lower()
            except KaggleAutomationError as exc:
                # A status check can itself transiently fail right after
                # `datasets create` returns - confirmed live (run
                # 31708887912): the very first `datasets status` call got a
                # bare "403 Client Error: Forbidden", the same
                # misleading-permission-error shape as the earlier
                # kernel-slug bug, really meaning the freshly created
                # dataset isn't visible to the API yet. Treated as "not
                # ready" and retried, the same way fetch_stage0.py already
                # retries real HTTP 429s, rather than propagated.
                last_status = f"<status check failed: {exc}>"
            else:
                if last_status == "ready":
                    return last_status
            if clock() - start >= timeout_sec:
                raise KaggleAutomationError(
                    f"Timed out after {timeout_sec}s waiting for dataset {dataset_ref.full_ref} "
                    f"to become ready (last status: {last_status!r})"
                )
            sleep_fn(poll_interval_sec)

    def download_dataset(self, dataset_ref: KaggleDatasetRef, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        args = [
            self._binary, "datasets", "download",
            "-d", dataset_ref.full_ref, "-p", str(dest_dir), "--unzip",
        ]
        self._run(args)
        return dest_dir

    def poll_dataset_downloadable(
        self,
        dataset_ref: KaggleDatasetRef,
        *,
        dest_dir: Path,
        poll_interval_sec: float = 10.0,
        timeout_sec: float = 180.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Blocks until `dataset_ref` is genuinely downloadable or
        `timeout_sec` elapses - the readiness check `dispatch_via_kaggle`
        actually needs before pushing a kernel that references a freshly
        created dataset. Confirmed live (infra/kaggle/diagnose_dataset_attach.py's
        push-kernel diagnostic, run 31795945773) that `datasets download`
        is a trustworthy readiness signal: it succeeded on the first
        attempt and the exact same production KernelPushConfig/push_kernel()
        code path then pushed clean, with no "not valid dataset sources"
        warning at all. `get_dataset_status`/`poll_dataset_until_ready`
        are NOT used here - that endpoint 403'd persistently across every
        real production attempt (see get_dataset_status's own docstring),
        so it was never a working readiness signal to begin with; the
        fixed-delay workaround that replaced it was a blind guess that
        never actually confirmed anything.

        Raises KaggleAutomationError on timeout - callers must treat that
        as a hard dispatch failure, not push a kernel referencing a
        dataset that was never confirmed ready."""
        start = clock()
        last_error: KaggleAutomationError | None = None
        while True:
            try:
                self.download_dataset(dataset_ref, dest_dir)
            except KaggleAutomationError as exc:
                last_error = exc
            else:
                return
            if clock() - start >= timeout_sec:
                raise KaggleAutomationError(
                    f"Timed out after {timeout_sec}s waiting for dataset {dataset_ref.full_ref} "
                    f"to become downloadable (last error: {last_error})"
                )
            sleep_fn(poll_interval_sec)

    def push_kernel(self, kernel_dir: Path, config: KernelPushConfig) -> str:
        config.validate()
        metadata_path = kernel_dir / "kernel-metadata.json"
        metadata_path.write_text(json.dumps(config.to_kernel_metadata_dict(), indent=2))
        args = [self._binary, "kernels", "push", "-p", str(kernel_dir)]
        return self._run(args).stdout

    def get_kernel_status(self, kernel_ref: KaggleKernelRef) -> KaggleKernelStatus:
        status, _raw = self._get_kernel_status_raw(kernel_ref)
        return status

    def _get_kernel_status_raw(self, kernel_ref: KaggleKernelRef) -> tuple[KaggleKernelStatus, str]:
        # `kaggle kernels status` prints a real `Failure message: "..."`
        # line (from the CLI's own kernels_status_cli) right after the
        # status line whenever a kernel errored - the actual reason the
        # run failed, for free, with no extra API call. get_kernel_status
        # discarded this by only ever returning the parsed enum; kept here
        # so poll_kernel_until_terminal can surface it via
        # KaggleJobResult.raw_status_output instead of a caller having to
        # separately download kernel output/log files to find out why.
        result = self._run([self._binary, "kernels", "status", kernel_ref.full_ref])
        return self._parse_status(result.stdout), result.stdout

    def pull_kernel_output(self, kernel_ref: KaggleKernelRef, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        args = [self._binary, "kernels", "output", kernel_ref.full_ref, "-p", str(dest_dir)]
        self._run(args)
        return dest_dir

    def poll_kernel_until_terminal(
        self,
        kernel_ref: KaggleKernelRef,
        *,
        poll_interval_sec: float = 30.0,
        timeout_sec: float = 3600.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> KaggleJobResult:
        """Blocks (via the injectable `sleep_fn`) until the kernel reaches
        a terminal status or `timeout_sec` elapses. Tests inject a no-op
        sleep_fn and a fake clock so this never actually waits in CI.

        A status check can itself transiently fail right after `kernels
        push` returns - confirmed live (run 31711116854): the very first
        `kernels status` call got "Permission 'kernels.get' was denied" on
        a kernel that had just been pushed successfully (to the exact slug
        `kernels push` itself reported back), so this wasn't a wrong-ref
        problem like the earlier dataset one - just the read API not
        having caught up yet. Treated as non-terminal and retried, the
        same way `poll_dataset_until_ready` treats a transient status-check
        failure, rather than propagated as a hard failure on the first
        check."""
        start = clock()
        last_status = KaggleKernelStatus.QUEUED
        while True:
            try:
                last_status, raw_status_output = self._get_kernel_status_raw(kernel_ref)
            except KaggleAutomationError:
                pass
            else:
                if last_status.is_terminal:
                    return KaggleJobResult(
                        kernel_ref=kernel_ref, status=last_status, elapsed_sec=clock() - start,
                        raw_status_output=raw_status_output,
                    )
            if clock() - start >= timeout_sec:
                raise KaggleAutomationError(
                    f"Timed out after {timeout_sec}s waiting for kernel {kernel_ref.full_ref} "
                    f"to finish (last status: {last_status.value})"
                )
            sleep_fn(poll_interval_sec)

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        result = self._runner(args)
        if result.returncode != 0:
            raise KaggleAutomationError(
                f"kaggle CLI command failed (exit {result.returncode}): {' '.join(args)}\n"
                f"stderr: {getattr(result, 'stderr', '')}"
            )
        return result

    @staticmethod
    def _parse_status(stdout: str) -> KaggleKernelStatus:
        match = _STATUS_PATTERN.search(stdout)
        if match is None:
            raise KaggleAutomationError(f"Could not parse kernel status from output: {stdout!r}")
        # A real `kernels status` call (confirmed by hand, run 30278022296)
        # prints the raw enum repr - `"KernelWorkerStatus.RUNNING"`, not
        # the bare `"running"` this originally assumed - because
        # kernels_status_cli() does `'%s' % response.status` on the enum
        # member itself. rsplit(".")[-1] strips that class-name prefix
        # when present and is a no-op on the plain values this codebase's
        # own tests use, so both keep working.
        raw = match.group(1).rsplit(".", 1)[-1].lower().replace("_", "")
        try:
            return KaggleKernelStatus(raw)
        except ValueError:
            if raw in ("cancelacknowledged", "cancelling", "cancelrequested"):
                return KaggleKernelStatus.CANCELLED
            raise KaggleAutomationError(f"Unrecognized kernel status: {raw!r}") from None
