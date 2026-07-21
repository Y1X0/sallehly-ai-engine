from __future__ import annotations

from typing import Any

QUALITY_PRESETS: dict[str, dict[str, Any]] = {
    "720p": {"resolution": "1280x720", "video_bitrate_kbps": 4000, "audio_bitrate_kbps": 128},
    "1080p": {"resolution": "1920x1080", "video_bitrate_kbps": 8000, "audio_bitrate_kbps": 192},
    "1440p": {"resolution": "2560x1440", "video_bitrate_kbps": 16000, "audio_bitrate_kbps": 192},
    "4k": {"resolution": "3840x2160", "video_bitrate_kbps": 35000, "audio_bitrate_kbps": 256},
}

FORMAT_CODECS: dict[str, dict[str, Any]] = {
    "mp4": {
        "video_codec": "libx264",
        "audio_codec": "aac",
        "extra_args": ["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
    },
    "mov": {
        "video_codec": "libx264",
        "audio_codec": "aac",
        "extra_args": ["-pix_fmt", "yuv420p"],
    },
    "webm": {
        "video_codec": "libvpx-vp9",
        "audio_codec": "libopus",
        "extra_args": [],
    },
}
