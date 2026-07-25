from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, MetaData, String, Table, Text, create_engine, select
from sqlalchemy.engine import Engine, Row

from .store import IProjectStore, ProjectRecord, ProjectStatus

metadata = MetaData()

projects_table = Table(
    "projects",
    metadata,
    Column("project_id", String, primary_key=True),
    Column("workspace_id", String, nullable=False, index=True),
    Column("created_by", String, nullable=False),
    Column("brief", Text, nullable=False),
    Column("status", String, nullable=False),
    Column("rejected_stage", String, nullable=True),
    Column("generation_job_ids", Text, nullable=False),
    Column("asset_ids", Text, nullable=False),
    Column("error_message", Text, nullable=True),
    Column("render_manifest", Text, nullable=True),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
)


class PostgresProjectStore(IProjectStore):
    """IProjectStore backed by a real Postgres table (Phase 8 WP2).

    Row bodies (`brief`, `generation_job_ids`, `asset_ids`,
    `render_manifest`) are stored as JSON text rather than Postgres JSONB
    columns - this table is only ever read/written a whole row at a time
    through ProjectRecord, never queried by JSON field, so JSONB's
    indexing/containment-query features would add nothing here.

    `save()` takes `SELECT ... FOR UPDATE` on the row before writing, so
    two concurrent writers to the same project (e.g. a retried Temporal
    activity racing a direct API call - docs/PHASE8_SCALEOUT_PLAN.md Risk
    2) serialize on the row lock instead of silently clobbering each
    other.
    """

    def __init__(self, database_url: str, *, echo: bool = False) -> None:
        self._engine: Engine = create_engine(database_url, echo=echo, future=True)
        metadata.create_all(self._engine)

    def create(self, record: ProjectRecord) -> None:
        with self._engine.begin() as conn:
            existing = conn.execute(
                select(projects_table.c.project_id).where(
                    projects_table.c.project_id == record.project_id
                )
            ).first()
            if existing is not None:
                raise ValueError(f"Project {record.project_id} already exists")
            conn.execute(projects_table.insert().values(**_to_row(record)))

    def get(self, project_id: str) -> ProjectRecord | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(projects_table).where(projects_table.c.project_id == project_id)
            ).first()
            return _from_row(row) if row is not None else None

    def save(self, record: ProjectRecord) -> None:
        record.updated_at = _now()
        with self._engine.begin() as conn:
            locked = conn.execute(
                select(projects_table.c.project_id)
                .where(projects_table.c.project_id == record.project_id)
                .with_for_update()
            ).first()
            if locked is None:
                raise ValueError(f"Project {record.project_id} does not exist")
            conn.execute(
                projects_table.update()
                .where(projects_table.c.project_id == record.project_id)
                .values(**_to_row(record))
            )

    def list_for_workspace(self, workspace_id: str) -> list[ProjectRecord]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(projects_table).where(projects_table.c.workspace_id == workspace_id)
            ).all()
            return [_from_row(row) for row in rows]


def _to_row(record: ProjectRecord) -> dict[str, Any]:
    return {
        "project_id": record.project_id,
        "workspace_id": record.workspace_id,
        "created_by": record.created_by,
        "brief": json.dumps(record.brief),
        "status": record.status.value,
        "rejected_stage": record.rejected_stage,
        "generation_job_ids": json.dumps(record.generation_job_ids),
        "asset_ids": json.dumps(record.asset_ids),
        "error_message": record.error_message,
        "render_manifest": json.dumps(record.render_manifest) if record.render_manifest is not None else None,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _from_row(row: Row) -> ProjectRecord:
    mapping = row._mapping
    return ProjectRecord(
        project_id=mapping["project_id"],
        workspace_id=mapping["workspace_id"],
        created_by=mapping["created_by"],
        brief=json.loads(mapping["brief"]),
        status=ProjectStatus(mapping["status"]),
        rejected_stage=mapping["rejected_stage"],
        generation_job_ids=json.loads(mapping["generation_job_ids"]),
        asset_ids=json.loads(mapping["asset_ids"]),
        error_message=mapping["error_message"],
        render_manifest=json.loads(mapping["render_manifest"]) if mapping["render_manifest"] is not None else None,
        created_at=mapping["created_at"],
        updated_at=mapping["updated_at"],
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
