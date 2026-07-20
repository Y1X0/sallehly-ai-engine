from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class IStorageProvider(ABC):
    """Where the platform persists bytes it owns (post-processed masters,
    thumbnails, exported deliverables) - distinct from the Asset Manager,
    which tracks *metadata about* an asset (versions, uris) regardless of
    which storage backend holds the bytes. Most Phase 3 assets (a RawClip
    fresh out of a Video Engine Adapter) already live wherever the compute
    provider uploaded them and are registered via their existing URI
    without going through this interface at all - this is for the cases
    where the platform itself needs to copy/persist something (e.g. a
    Post-Processing master, Phase 5).
    """

    @abstractmethod
    def put(self, key: str, source_path: str | Path) -> str:
        """Persist the file at source_path under `key`, returning its URI."""
        ...

    @abstractmethod
    def get_uri(self, key: str) -> str: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...
