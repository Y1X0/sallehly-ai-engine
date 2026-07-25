from __future__ import annotations

from typing import Any

import schemas

from ._util import new_id, now_iso

_KIND_REQUIRES_SUBJECT = {"character", "object", "environment"}


class ReferenceImageEngineError(Exception):
    """Raised when kind='character'/'object'/'environment' is used
    without a subject_id, or an assembled ReferencePackage fails schema
    validation."""


class ReferenceImageEngine:
    """Builds reusable ReferencePackages (reference_package.schema.json)
    from one or more reference images for a character, object,
    environment, or the project's overall style/pose vocabulary. A
    package is a bundle of asset ids plus their role (primary/angle/
    detail/pose/mood) - ready to be handed to a future conditioning-
    capable engine adapter. `prepared_for` only records readiness
    (whether this package is *structured* for ControlNet/IP-Adapter
    input); it never causes any conditioning to actually run - see
    IReferenceConditioningAdapter (packages/cinematic-intelligence-sdk)
    and docs/adr/0013-cinematic-intelligence-layer.md."""

    def __init__(self) -> None:
        self._packages: dict[str, dict[str, Any]] = {}

    def create(
        self,
        project_id: str,
        kind: str,
        images: list[dict[str, Any]],
        *,
        subject_id: str | None = None,
        package_id: str | None = None,
        prepared_for: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        if kind in _KIND_REQUIRES_SUBJECT and not subject_id:
            raise ReferenceImageEngineError(f"kind={kind!r} requires a subject_id")

        package: dict[str, Any] = {
            "schema_version": "1.0",
            "package_id": package_id or new_id("ref"),
            "project_id": project_id,
            "kind": kind,
            "images": images,
            "created_at": now_iso(),
        }
        if subject_id:
            package["subject_id"] = subject_id
        if prepared_for:
            package["prepared_for"] = prepared_for

        try:
            schemas.validate(package, "reference_package")
        except Exception as exc:  # noqa: BLE001
            raise ReferenceImageEngineError(f"Assembled ReferencePackage failed validation: {exc}") from exc

        self._packages[package["package_id"]] = package
        return package

    def character_package(self, project_id: str, character_id: str, images: list[dict[str, Any]]) -> dict[str, Any]:
        return self.create(project_id, "character", images, subject_id=character_id)

    def object_package(self, project_id: str, object_id: str, images: list[dict[str, Any]]) -> dict[str, Any]:
        return self.create(project_id, "object", images, subject_id=object_id)

    def environment_package(
        self, project_id: str, environment_id: str, images: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return self.create(project_id, "environment", images, subject_id=environment_id)

    def style_package(self, project_id: str, images: list[dict[str, Any]]) -> dict[str, Any]:
        return self.create(project_id, "style", images)

    def pose_package(self, project_id: str, images: list[dict[str, Any]]) -> dict[str, Any]:
        return self.create(project_id, "pose", images)

    def get(self, package_id: str) -> dict[str, Any]:
        try:
            return self._packages[package_id]
        except KeyError:
            raise ReferenceImageEngineError(f"No ReferencePackage {package_id!r}") from None

    def list_for_subject(self, project_id: str, subject_id: str) -> list[dict[str, Any]]:
        return [
            p
            for p in self._packages.values()
            if p["project_id"] == project_id and p.get("subject_id") == subject_id
        ]

    def list_for_project(self, project_id: str) -> list[dict[str, Any]]:
        return [p for p in self._packages.values() if p["project_id"] == project_id]
