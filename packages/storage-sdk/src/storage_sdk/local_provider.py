from __future__ import annotations

import shutil
from pathlib import Path

from .provider import IStorageProvider

_DEFAULT_ROOT = "./.docker-data/asset-storage"


class LocalFilesystemStorageProvider(IStorageProvider):
    """Dev/test IStorageProvider: copies files under a local root
    directory and returns file:// URIs. Mirrors MinIO locally the same
    way LocalProvider (packages/video-engine-sdk consumer,
    services/video-engine-adapter) mirrors a real compute backend -
    same shape, no external dependency, safe for tests.
    """

    def __init__(self, root_dir: str | Path = _DEFAULT_ROOT) -> None:
        self._root = Path(root_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, source_path: str | Path) -> str:
        destination = self._root / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = Path(source_path)
        if source.resolve() != destination.resolve():
            shutil.copyfile(source, destination)
        return self.get_uri(key)

    def get_uri(self, key: str) -> str:
        return f"file://{(self._root / key).resolve()}"

    def exists(self, key: str) -> bool:
        return (self._root / key).exists()
