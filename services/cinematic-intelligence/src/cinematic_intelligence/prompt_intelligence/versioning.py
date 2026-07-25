from __future__ import annotations

from typing import Any


class PromptVersioning:
    """In-memory version history for a shot's PromptPackages. Every time
    the Prompt Intelligence Engine (re)builds a shot's prompt - the
    initial build, or a later rebuild triggered by an Automatic Repair
    Engine `prompt_repair` action - the new PromptPackage is recorded
    here at an incremented `version`, and the full history stays
    available for audit."""

    def __init__(self) -> None:
        self._history: dict[str, list[dict[str, Any]]] = {}

    def record(self, package: dict[str, Any]) -> dict[str, Any]:
        self._history.setdefault(package["shot_id"], []).append(package)
        return package

    def next_version(self, shot_id: str) -> int:
        history = self._history.get(shot_id, [])
        return (history[-1]["version"] + 1) if history else 1

    def history(self, shot_id: str) -> list[dict[str, Any]]:
        return list(self._history.get(shot_id, []))

    def latest(self, shot_id: str) -> dict[str, Any] | None:
        history = self._history.get(shot_id)
        return history[-1] if history else None
