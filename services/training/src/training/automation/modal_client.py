from __future__ import annotations

import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable

from .errors import ModalAutomationError, ModalCLINotAvailableError

Runner = Callable[[list[str]], subprocess.CompletedProcess]

_APP_ID_PATTERN = re.compile(r"\b(ap-[A-Za-z0-9]+)\b")


class GPUType(str, Enum):
    """Modal's real GPU string identifiers, as used in
    `@app.function(gpu="...")` / `modal run script.py::fn --gpu ...`.
    Kept as an explicit enum (rather than a free string) so a config
    generator can only ever select a GPU class this client actually
    knows the relative cost/availability tradeoffs for."""

    T4 = "T4"
    L4 = "L4"
    A10G = "A10G"
    A100 = "A100-40GB"
    A100_80GB = "A100-80GB"
    H100 = "H100"
    B200 = "B200"


@dataclass
class ModalJobConfig:
    """Describes one `modal run --detach` invocation. `function_timeout_sec`
    documents the timeout the target entrypoint's own `@app.function(...)`
    decorator is expected to declare (Modal has no CLI flag for this - it
    is a property of the deployed function itself); `max_wall_clock_sec`
    is this launcher's own belt-and-suspenders ceiling, enforced by
    polling and an explicit `modal app stop` if the function's own
    timeout is somehow not honored. `extra_args` become `--key value`
    flags appended to `modal run`, mirroring how Modal auto-generates a
    CLI for a function's own parameters."""

    app_entrypoint: str
    function_name: str
    gpu_type: GPUType
    function_timeout_sec: int
    max_wall_clock_sec: int
    extra_args: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.app_entrypoint.strip():
            raise ValueError("ModalJobConfig.app_entrypoint must not be empty")
        if not self.function_name.strip():
            raise ValueError("ModalJobConfig.function_name must not be empty")
        if self.function_timeout_sec <= 0:
            raise ValueError("function_timeout_sec must be positive")
        if self.max_wall_clock_sec <= 0:
            raise ValueError("max_wall_clock_sec must be positive")
        if self.max_wall_clock_sec < self.function_timeout_sec:
            raise ValueError(
                "max_wall_clock_sec must be >= function_timeout_sec - the launcher's "
                "safety ceiling should never trip before the function's own declared timeout"
            )

    def to_cli_args(self, binary: str) -> list[str]:
        args = [binary, "run", "--detach", f"{self.app_entrypoint}::{self.function_name}"]
        for key, value in self.extra_args.items():
            args.extend([f"--{key}", value])
        return args


@dataclass(frozen=True)
class ModalJobHandle:
    app_name: str
    started_at: datetime
    raw_launch_output: str = ""


def _default_binary_path() -> str:
    path = shutil.which("modal")
    if path is None:
        raise ModalCLINotAvailableError(
            "The `modal` CLI is not installed or not on PATH. Install with "
            "`pip install modal` and run `modal setup` - see docs/DEV_SETUP.md."
        )
    return path


class ModalJobLauncher:
    """Real wrapper around the `modal` CLI for launching, monitoring, and
    force-stopping serverless GPU jobs - Phase 2's other automatable free
    path from the training-factory architecture report ($30/month free
    compute, no card required).

    "Automatic shutdown after completion" is a property Modal's own
    serverless billing model already guarantees (a function that returns
    scales the container to zero immediately, billed per-second) - this
    class does not need to, and does not try to, reimplement that. What
    it does add is a belt-and-suspenders ceiling: enforce_wall_clock_ceiling()
    calls `modal app stop` if a job somehow runs past
    ModalJobConfig.max_wall_clock_sec, so a hung job can never silently
    keep billing.

    As with KaggleClient, a `runner` can be injected in place of
    `subprocess.run` so tests never touch a real `modal` CLI or network.
    """

    def __init__(self, *, runner: Runner | None = None, cli_path: str | None = None) -> None:
        if runner is not None:
            self._runner: Runner = runner
            self._binary = cli_path or "modal"
        else:
            self._binary = cli_path or _default_binary_path()
            self._runner = subprocess.run

    def launch(self, config: ModalJobConfig) -> ModalJobHandle:
        config.validate()
        args = config.to_cli_args(self._binary)
        result = self._run(args)
        app_name = self._parse_app_id(result.stdout) or config.app_entrypoint
        return ModalJobHandle(
            app_name=app_name,
            started_at=datetime.now(timezone.utc),
            raw_launch_output=result.stdout,
        )

    def fetch_logs(self, handle: ModalJobHandle, *, follow: bool = False) -> str:
        args = [self._binary, "app", "logs", handle.app_name]
        if follow:
            args.append("-f")
        return self._run(args).stdout

    def stop(self, handle: ModalJobHandle) -> None:
        self._run([self._binary, "app", "stop", handle.app_name])

    def enforce_wall_clock_ceiling(
        self,
        handle: ModalJobHandle,
        config: ModalJobConfig,
        *,
        is_complete: Callable[[ModalJobHandle], bool],
        poll_interval_sec: float = 30.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> bool:
        """Polls `is_complete(handle)` (caller-supplied, since completion
        detection is app-specific - e.g. checking for a result file in
        storage) until it returns True or `config.max_wall_clock_sec`
        elapses, in which case `stop()` is called and False is returned.
        Returns True if the job finished on its own before the ceiling.
        Tests inject a fake clock/sleep_fn so this never actually waits.
        """
        start = clock()
        while True:
            if is_complete(handle):
                return True
            if clock() - start >= config.max_wall_clock_sec:
                self.stop(handle)
                return False
            sleep_fn(poll_interval_sec)

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        result = self._runner(args)
        if result.returncode != 0:
            raise ModalAutomationError(
                f"modal CLI command failed (exit {result.returncode}): {' '.join(args)}\n"
                f"stderr: {getattr(result, 'stderr', '')}"
            )
        return result

    @staticmethod
    def _parse_app_id(stdout: str) -> str | None:
        match = _APP_ID_PATTERN.search(stdout)
        return match.group(1) if match else None
