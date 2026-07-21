from __future__ import annotations

import shutil
from pathlib import Path

from video_composition_sdk import IUpscaler


class PassthroughUpscaler(IUpscaler):
    """The only concrete IUpscaler today: copies input to output
    unchanged. Real upscaling (e.g. Real-ESRGAN-style super-resolution)
    and frame interpolation (e.g. RIFE) both need a GPU model
    deployment - the same class of limitation as Wan2.1 inference (ADR
    0010), not something this environment can execute. This exists so
    the rest of the pipeline (Export Service quality presets, a future
    "enhance before export" step) can be built and tested against
    IUpscaler now, and swapped for a real implementation later without
    any caller changing - the same "interface + honest stub" pattern as
    every other not-yet-executable boundary in this codebase.
    """

    def upscale(self, input_path: str | Path, output_path: str | Path, target_resolution: str) -> str:
        shutil.copyfile(input_path, output_path)
        return str(output_path)

    def interpolate_frames(self, input_path: str | Path, output_path: str | Path, target_fps: int) -> str:
        shutil.copyfile(input_path, output_path)
        return str(output_path)
