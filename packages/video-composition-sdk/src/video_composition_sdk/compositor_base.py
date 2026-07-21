from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from .types import CompositionResult, SubtitleTrack, Timeline


class IRenderCompositor(ABC):
    """How a Timeline (sequenced video clips + transitions + audio
    tracks + an optional subtitle track + watermark) becomes one
    assembled master video file. This is the engine-agnostic boundary
    for post-production - the same role IVideoEngine plays for
    generation (ADR 0001/0002): swapping the concrete compositor (ffmpeg
    locally today, a cloud rendering service later) never requires
    changing TimelineBuilder, the Transition Engine, the Audio Pipeline,
    or the Subtitle System, which only ever produce/consume a Timeline.
    """

    @abstractmethod
    def compose(
        self,
        timeline: Timeline,
        output_path: str | Path,
        subtitle_track: SubtitleTrack | None = None,
    ) -> CompositionResult: ...
