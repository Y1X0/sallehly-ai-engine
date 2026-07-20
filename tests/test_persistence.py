from __future__ import annotations

import pytest
import schemas
from persistence import InMemoryProjectStore, ProjectRecord, ProjectStatus


def _record(project_id: str = "proj_1") -> ProjectRecord:
    return ProjectRecord(
        project_id=project_id,
        workspace_id="ws1",
        created_by="user1",
        brief={"prompt": "x", "target_duration_sec": 10, "aspect_ratio": "16:9"},
    )


def test_create_and_get():
    store = InMemoryProjectStore()
    store.create(_record())
    fetched = store.get("proj_1")
    assert fetched is not None
    assert fetched.status == ProjectStatus.CREATED


def test_create_twice_raises():
    store = InMemoryProjectStore()
    store.create(_record())
    with pytest.raises(ValueError):
        store.create(_record())


def test_get_missing_returns_none():
    store = InMemoryProjectStore()
    assert store.get("does-not-exist") is None


def test_save_updates_and_bumps_updated_at():
    store = InMemoryProjectStore()
    record = _record()
    store.create(record)
    original_updated_at = record.updated_at

    record.status = ProjectStatus.PLANNING
    store.save(record)

    fetched = store.get("proj_1")
    assert fetched.status == ProjectStatus.PLANNING
    assert fetched.updated_at >= original_updated_at


def test_list_for_workspace_filters_correctly():
    store = InMemoryProjectStore()
    store.create(_record("proj_1"))
    other = _record("proj_2")
    other.workspace_id = "ws2"
    store.create(other)

    assert [r.project_id for r in store.list_for_workspace("ws1")] == ["proj_1"]
    assert [r.project_id for r in store.list_for_workspace("ws2")] == ["proj_2"]


def test_project_record_to_dict_is_schema_valid():
    record = _record()
    schemas.validate(record.to_dict(), "project")

    record.status = ProjectStatus.COMPLETED
    record.generation_job_ids = ["job_1"]
    record.asset_ids = ["asset_1"]
    schemas.validate(record.to_dict(), "project")

    record.status = ProjectStatus.FAILED
    record.error_message = "shot_0_0 failed"
    schemas.validate(record.to_dict(), "project")
