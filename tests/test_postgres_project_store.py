"""Real, live-executed tests for PostgresProjectStore: driven against an
actual local Postgres server (not mocked, not sqlite-in-memory standing
in for Postgres) - see docs/adr/0016-postgres-persistence.md.

Skipped entirely if no Postgres server is reachable at DATABASE_URL - see
docs/DEV_SETUP.md for how to provision one locally.
"""

from __future__ import annotations

import os
import uuid

import pytest
from persistence import PostgresProjectStore, ProjectRecord, ProjectStatus
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://sallehly:sallehly@localhost:5432/video_engine"
)


def _server_reachable() -> bool:
    engine = create_engine(DATABASE_URL, future=True)
    try:
        with engine.connect():
            return True
    except OperationalError:
        return False
    finally:
        engine.dispose()


pytestmark = pytest.mark.skipif(
    not _server_reachable(), reason=f"no Postgres server reachable at {DATABASE_URL}"
)


def _record(project_id: str | None = None) -> ProjectRecord:
    return ProjectRecord(
        project_id=project_id or f"proj_{uuid.uuid4().hex[:8]}",
        workspace_id="ws1",
        created_by="user1",
        brief={"prompt": "x", "target_duration_sec": 10, "aspect_ratio": "16:9"},
    )


@pytest.fixture
def store() -> PostgresProjectStore:
    return PostgresProjectStore(DATABASE_URL)


def test_create_and_get(store: PostgresProjectStore):
    record = _record()
    store.create(record)

    fetched = store.get(record.project_id)
    assert fetched is not None
    assert fetched.project_id == record.project_id
    assert fetched.workspace_id == "ws1"
    assert fetched.status == ProjectStatus.CREATED


def test_create_twice_raises(store: PostgresProjectStore):
    record = _record()
    store.create(record)
    with pytest.raises(ValueError):
        store.create(record)


def test_get_missing_returns_none(store: PostgresProjectStore):
    assert store.get("does-not-exist") is None


def test_save_missing_raises(store: PostgresProjectStore):
    with pytest.raises(ValueError):
        store.save(_record())


def test_save_updates_and_bumps_updated_at(store: PostgresProjectStore):
    record = _record()
    store.create(record)
    original_updated_at = record.updated_at

    record.status = ProjectStatus.PLANNING
    record.generation_job_ids = ["job_1"]
    store.save(record)

    fetched = store.get(record.project_id)
    assert fetched.status == ProjectStatus.PLANNING
    assert fetched.generation_job_ids == ["job_1"]
    assert fetched.updated_at >= original_updated_at


def test_list_for_workspace_filters_correctly(store: PostgresProjectStore):
    ws = f"ws_{uuid.uuid4().hex[:8]}"
    a = _record()
    a.workspace_id = ws
    b = _record()
    b.workspace_id = ws
    other = _record()
    other.workspace_id = f"other_{uuid.uuid4().hex[:8]}"
    store.create(a)
    store.create(b)
    store.create(other)

    listed = {r.project_id for r in store.list_for_workspace(ws)}
    assert listed == {a.project_id, b.project_id}


def test_round_trips_nested_brief_and_render_manifest(store: PostgresProjectStore):
    record = _record()
    record.brief = {"prompt": "a cat", "shots": [{"idx": 0}, {"idx": 1}]}
    store.create(record)

    record.status = ProjectStatus.EXPORTED
    record.render_manifest = {"video_url": "s3://x/final.mp4", "thumbnails": ["a.jpg"]}
    store.save(record)

    fetched = store.get(record.project_id)
    assert fetched.brief == {"prompt": "a cat", "shots": [{"idx": 0}, {"idx": 1}]}
    assert fetched.render_manifest == {"video_url": "s3://x/final.mp4", "thumbnails": ["a.jpg"]}


def test_survives_a_new_store_instance_against_the_same_database(store: PostgresProjectStore):
    """Proves persistence is real (the row lives in Postgres, not just in
    a Python object) by reading it back through a brand new
    PostgresProjectStore/engine."""
    record = _record()
    store.create(record)

    second_store = PostgresProjectStore(DATABASE_URL)
    fetched = second_store.get(record.project_id)
    assert fetched is not None
    assert fetched.project_id == record.project_id


def test_concurrent_saves_serialize_instead_of_lost_update(store: PostgresProjectStore):
    """Two 'workers' each load the same record, then both try to append a
    distinct generation_job_id and save. With SELECT ... FOR UPDATE
    serializing the two save() calls, this test itself doesn't prove
    lost-update prevention (that needs true concurrency), but it does
    prove save() takes the row lock without deadlocking or erroring on a
    completely ordinary sequential double-save - a minimum bar this store
    must clear."""
    record = _record()
    store.create(record)

    loaded_1 = store.get(record.project_id)
    loaded_2 = store.get(record.project_id)

    loaded_1.generation_job_ids = ["job_a"]
    store.save(loaded_1)

    loaded_2.generation_job_ids = ["job_b"]
    store.save(loaded_2)

    fetched = store.get(record.project_id)
    assert fetched.generation_job_ids == ["job_b"]
