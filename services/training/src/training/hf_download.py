from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .wan22.registry_metadata import Wan22RegistryEntry

_HASH_CHUNK_BYTES = 1024 * 1024
_DEFAULT_CACHE_ROOT = Path(".models-cache")

SnapshotDownloadFn = Callable[..., str]


class HFDownloadError(Exception):
    """Raised on any real failure fetching or verifying a Hugging Face
    Hub snapshot - network error, missing HF_TOKEN for a gated repo, or
    a downloaded file that doesn't match its recorded checksum on a
    later `verify()` call."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class DownloadManifest:
    """What actually landed on disk for one engine's weights - real
    per-file SHA-256 hashes computed after the download, not merely "the
    download command exited 0". `verify()` re-hashes every recorded file
    and fails loudly if anything has changed or gone missing, so a
    corrupted or partially-overwritten local cache is never silently
    trusted."""

    engine_id: str
    repo_id: str
    revision: str
    local_dir: str
    files: dict[str, str]  # relative path -> sha256
    downloaded_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "repo_id": self.repo_id,
            "revision": self.revision,
            "local_dir": self.local_dir,
            "files": self.files,
            "downloaded_at": self.downloaded_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DownloadManifest":
        return cls(
            engine_id=data["engine_id"],
            repo_id=data["repo_id"],
            revision=data["revision"],
            local_dir=data["local_dir"],
            files=dict(data["files"]),
            downloaded_at=data["downloaded_at"],
        )

    def verify(self) -> None:
        """Re-hashes every file this manifest recorded and raises
        `HFDownloadError` on the first mismatch or missing file - the
        real "validation" step required before trusting a cached
        download for a training run."""
        root = Path(self.local_dir)
        for relative_path, expected_hash in self.files.items():
            path = root / relative_path
            if not path.is_file():
                raise HFDownloadError(
                    f"{self.engine_id}: expected file missing from local cache: {path} "
                    "(re-run download_wan22_weights.py)"
                )
            actual_hash = _file_sha256(path)
            if actual_hash != expected_hash:
                raise HFDownloadError(
                    f"{self.engine_id}: checksum mismatch for {path} (expected {expected_hash}, got "
                    f"{actual_hash}) - the local cache is corrupted or was modified; re-run "
                    "download_wan22_weights.py"
                )


def _manifest_path(cache_root: Path, engine_id: str) -> Path:
    return cache_root / engine_id / "download_manifest.json"


def resolve_local_weights(engine_id: str, *, cache_root: str | Path = _DEFAULT_CACHE_ROOT) -> DownloadManifest | None:
    """Looks up a previously-completed, verified download for `engine_id`.
    Returns `None` (never raises) if nothing has been downloaded yet -
    callers (e.g. `training.wan22.diffusers_backend.default_model_sources`)
    use this to decide whether real weights are available or a caller
    must fall back to the smoke-test path."""
    path = _manifest_path(Path(cache_root), engine_id)
    if not path.is_file():
        return None
    return DownloadManifest.from_dict(json.loads(path.read_text()))


class HuggingFaceWeightsDownloader:
    """Real wrapper around `huggingface_hub.snapshot_download` for
    fetching one Wan2.2 engine's weights per its `models/registry.yaml`
    `download:` block. A `download_fn` can be injected in place of the
    real `snapshot_download` (same pattern `KaggleClient`/
    `ModalJobLauncher` already use for `subprocess.run`) so tests never
    touch the network or download multi-GB weights.

    This class never decides *whether* a download should happen for
    real - that's the caller's call (typically a human running
    `services/training/scripts/download_wan22_weights.py` once, ahead of
    a real GPU training job). It only performs the download, records a
    real per-file checksum manifest, and lets `resolve_local_weights()`/
    `DownloadManifest.verify()` confirm the result is trustworthy later.
    """

    def __init__(
        self,
        *,
        cache_root: str | Path = _DEFAULT_CACHE_ROOT,
        download_fn: SnapshotDownloadFn | None = None,
        hf_token: str | None = None,
    ) -> None:
        self._cache_root = Path(cache_root)
        self._hf_token = hf_token
        if download_fn is not None:
            self._download_fn = download_fn
        else:
            self._download_fn = self._real_snapshot_download

    def download(self, entry: Wan22RegistryEntry, *, force: bool = False) -> DownloadManifest:
        """Fetches `entry.download.repo_id`@`entry.download.revision`
        (restricted to `entry.download.allow_patterns`) into
        `cache_root/<engine_id>/`, hashes every file that landed, writes
        `download_manifest.json`, and returns the resulting
        `DownloadManifest`. If a verified manifest already exists and
        `force=False`, returns it without re-downloading."""
        if not force:
            existing = resolve_local_weights(entry.engine_id, cache_root=self._cache_root)
            if existing is not None:
                existing.verify()
                return existing

        target_dir = self._cache_root / entry.engine_id
        target_dir.mkdir(parents=True, exist_ok=True)

        local_dir = self._download_fn(
            repo_id=entry.download.repo_id,
            revision=entry.download.revision,
            allow_patterns=list(entry.download.allow_patterns) or None,
            local_dir=str(target_dir),
            token=self._hf_token,
        )
        local_dir_path = Path(local_dir)

        files: dict[str, str] = {}
        for path in sorted(local_dir_path.rglob("*")):
            if path.is_file():
                files[str(path.relative_to(local_dir_path))] = _file_sha256(path)

        if not files:
            raise HFDownloadError(
                f"{entry.engine_id}: download from {entry.download.repo_id!r} produced no files under "
                f"{local_dir_path} - check allow_patterns ({entry.download.allow_patterns!r}) against the "
                "repo's real file listing"
            )

        manifest = DownloadManifest(
            engine_id=entry.engine_id,
            repo_id=entry.download.repo_id,
            revision=entry.download.revision,
            local_dir=str(local_dir_path.resolve()),
            files=files,
            downloaded_at=_now(),
        )
        _manifest_path(self._cache_root, entry.engine_id).write_text(json.dumps(manifest.to_dict(), indent=2))
        return manifest

    @staticmethod
    def _real_snapshot_download(**kwargs: Any) -> str:
        try:
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise HFDownloadError(
                "huggingface_hub is not installed - install the training[gpu-training] extra "
                "(`uv sync --all-packages --extra gpu-training`) before downloading real weights"
            ) from exc
        try:
            return snapshot_download(**kwargs)
        except Exception as exc:  # noqa: BLE001 - real network/auth/repo errors, surfaced clearly
            raise HFDownloadError(f"huggingface_hub.snapshot_download failed: {exc}") from exc
