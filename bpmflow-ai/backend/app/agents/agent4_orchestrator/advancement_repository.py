"""Persistence for process advancement runs (REST + in-memory)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx

from app.core.logging import get_logger
from app.core.supabase_rest import (
    rest_insert,
    rest_select,
    rest_update,
    supabase_rest_configured,
    use_supabase_rest_fallback,
)

logger = get_logger(__name__)

from .advancement_schemas import AdvancementRunRecord, AdvancementRunStatus, AutonomousAction
from .constants import WorkflowStage


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _row_to_record(row: dict) -> AdvancementRunRecord:
    steps_raw = row.get("steps_json") or []
    steps: list[AutonomousAction] = []
    for item in steps_raw:
        if isinstance(item, dict):
            steps.append(AutonomousAction.model_validate(item))
    return AdvancementRunRecord(
        id=UUID(str(row["id"])),
        process_id=UUID(str(row["process_id"])),
        correlation_id=UUID(str(row["correlation_id"])),
        idempotency_key=str(row["idempotency_key"]),
        tenant_id=UUID(str(row["tenant_id"])) if row.get("tenant_id") else None,
        performed_by=UUID(str(row["performed_by"])) if row.get("performed_by") else None,
        task_id=UUID(str(row["task_id"])) if row.get("task_id") else None,
        from_stage=WorkflowStage(row["from_stage"]),
        current_stage=WorkflowStage(row["current_stage"]),
        status=AdvancementRunStatus(row["status"]),
        steps=steps,
        result_json=row.get("result_json") if isinstance(row.get("result_json"), dict) else None,
        error_code=row.get("error_code"),
        error_message=row.get("error_message"),
        created_at=datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00")),
        updated_at=datetime.fromisoformat(str(row["updated_at"]).replace("Z", "+00:00")),
        completed_at=(
            datetime.fromisoformat(str(row["completed_at"]).replace("Z", "+00:00"))
            if row.get("completed_at")
            else None
        ),
    )


class AdvancementRepository(ABC):
    @abstractmethod
    async def get_by_idempotency(
        self, process_id: UUID, idempotency_key: str
    ) -> AdvancementRunRecord | None:
        raise NotImplementedError

    @abstractmethod
    async def create_run(
        self,
        *,
        process_id: UUID,
        correlation_id: UUID,
        idempotency_key: str,
        from_stage: WorkflowStage,
        current_stage: WorkflowStage,
        tenant_id: UUID | None,
        performed_by: UUID | None,
        task_id: UUID | None,
    ) -> AdvancementRunRecord:
        raise NotImplementedError

    @abstractmethod
    async def update_run(self, record: AdvancementRunRecord) -> AdvancementRunRecord:
        raise NotImplementedError

    @abstractmethod
    async def list_stale_running(
        self, *, older_than: datetime, limit: int = 50
    ) -> list[AdvancementRunRecord]:
        raise NotImplementedError


class InMemoryAdvancementRepository(AdvancementRepository):
    def __init__(self) -> None:
        self._runs: dict[UUID, AdvancementRunRecord] = {}
        self._idempotency: dict[tuple[UUID, str], UUID] = {}

    async def get_by_idempotency(
        self, process_id: UUID, idempotency_key: str
    ) -> AdvancementRunRecord | None:
        run_id = self._idempotency.get((process_id, idempotency_key))
        if run_id is None:
            return None
        return self._runs.get(run_id)

    async def create_run(
        self,
        *,
        process_id: UUID,
        correlation_id: UUID,
        idempotency_key: str,
        from_stage: WorkflowStage,
        current_stage: WorkflowStage,
        tenant_id: UUID | None,
        performed_by: UUID | None,
        task_id: UUID | None,
    ) -> AdvancementRunRecord:
        existing = await self.get_by_idempotency(process_id, idempotency_key)
        if existing is not None:
            return existing
        now = _utc_now()
        record = AdvancementRunRecord(
            id=uuid4(),
            process_id=process_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            tenant_id=tenant_id,
            performed_by=performed_by,
            task_id=task_id,
            from_stage=from_stage,
            current_stage=current_stage,
            status=AdvancementRunStatus.RUNNING,
            created_at=now,
            updated_at=now,
        )
        self._runs[record.id] = record
        self._idempotency[(process_id, idempotency_key)] = record.id
        return record

    async def update_run(self, record: AdvancementRunRecord) -> AdvancementRunRecord:
        record = record.model_copy(update={"updated_at": _utc_now()})
        self._runs[record.id] = record
        return record

    async def list_stale_running(
        self, *, older_than: datetime, limit: int = 50
    ) -> list[AdvancementRunRecord]:
        items = [
            r
            for r in self._runs.values()
            if r.status is AdvancementRunStatus.RUNNING and r.updated_at < older_than
        ]
        items.sort(key=lambda r: r.updated_at)
        return items[:limit]


class RestAdvancementRepository(AdvancementRepository):
    """Supabase REST persistence for advancement runs."""

    async def get_by_idempotency(
        self, process_id: UUID, idempotency_key: str
    ) -> AdvancementRunRecord | None:
        rows = rest_select(
            "process_advancement_runs",
            {
                "process_id": f"eq.{process_id}",
                "idempotency_key": f"eq.{idempotency_key}",
                "select": "*",
                "limit": "1",
            },
        )
        if not rows:
            return None
        return _row_to_record(rows[0])

    async def create_run(
        self,
        *,
        process_id: UUID,
        correlation_id: UUID,
        idempotency_key: str,
        from_stage: WorkflowStage,
        current_stage: WorkflowStage,
        tenant_id: UUID | None,
        performed_by: UUID | None,
        task_id: UUID | None,
    ) -> AdvancementRunRecord:
        existing = await self.get_by_idempotency(process_id, idempotency_key)
        if existing is not None:
            return existing
        now = _utc_now().isoformat()
        row = rest_insert(
            "process_advancement_runs",
            {
                "process_id": str(process_id),
                "correlation_id": str(correlation_id),
                "idempotency_key": idempotency_key,
                "tenant_id": str(tenant_id) if tenant_id else None,
                "performed_by": str(performed_by) if performed_by else None,
                "task_id": str(task_id) if task_id else None,
                "from_stage": from_stage.value,
                "current_stage": current_stage.value,
                "status": AdvancementRunStatus.RUNNING.value,
                "steps_json": [],
                "created_at": now,
                "updated_at": now,
            },
        )
        return _row_to_record(row)

    async def update_run(self, record: AdvancementRunRecord) -> AdvancementRunRecord:
        now = _utc_now().isoformat()
        payload = {
            "current_stage": record.current_stage.value,
            "status": record.status.value,
            "steps_json": [s.model_dump(mode="json") for s in record.steps],
            "result_json": record.result_json,
            "error_code": record.error_code,
            "error_message": record.error_message,
            "updated_at": now,
            "completed_at": record.completed_at.isoformat() if record.completed_at else None,
        }
        rest_update(
            "process_advancement_runs",
            {"id": f"eq.{record.id}"},
            payload,
        )
        return record.model_copy(update={"updated_at": _utc_now()})

    async def list_stale_running(
        self, *, older_than: datetime, limit: int = 50
    ) -> list[AdvancementRunRecord]:
        rows = rest_select(
            "process_advancement_runs",
            {
                "status": f"eq.{AdvancementRunStatus.RUNNING.value}",
                "updated_at": f"lt.{older_than.isoformat()}",
                "select": "*",
                "order": "updated_at.asc",
                "limit": str(limit),
            },
        )
        return [_row_to_record(row) for row in rows]


def _rest_table_available(table: str) -> bool:
    if not supabase_rest_configured():
        return False
    try:
        rest_select(table, {"select": "id", "limit": "1"})
        return True
    except httpx.HTTPStatusError as exc:
        body = (exc.response.text or "").lower()
        if exc.response.status_code == 404 and "could not find the table" in body:
            return False
        raise
    except Exception:
        return False


class ResilientAdvancementRepository(AdvancementRepository):
    """Prefer REST idempotency rows; fall back to in-memory when migration 0014 is missing."""

    def __init__(self) -> None:
        self._memory = InMemoryAdvancementRepository()
        self._rest = RestAdvancementRepository()
        self._use_rest = _rest_table_available("process_advancement_runs")
        if not self._use_rest:
            logger.warning(
                "advancement_repository_degraded",
                extra={"reason": "process_advancement_runs table unavailable"},
            )

    def _active(self) -> AdvancementRepository:
        return self._rest if self._use_rest else self._memory

    async def get_by_idempotency(
        self, process_id: UUID, idempotency_key: str
    ) -> AdvancementRunRecord | None:
        return await self._active().get_by_idempotency(process_id, idempotency_key)

    async def create_run(
        self,
        *,
        process_id: UUID,
        correlation_id: UUID,
        idempotency_key: str,
        from_stage: WorkflowStage,
        current_stage: WorkflowStage,
        tenant_id: UUID | None,
        performed_by: UUID | None,
        task_id: UUID | None,
    ) -> AdvancementRunRecord:
        return await self._active().create_run(
            process_id=process_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            from_stage=from_stage,
            current_stage=current_stage,
            tenant_id=tenant_id,
            performed_by=performed_by,
            task_id=task_id,
        )

    async def update_run(self, record: AdvancementRunRecord) -> AdvancementRunRecord:
        return await self._active().update_run(record)

    async def list_stale_running(
        self, *, older_than: datetime, limit: int = 50
    ) -> list[AdvancementRunRecord]:
        return await self._active().list_stale_running(older_than=older_than, limit=limit)


def get_advancement_repository() -> AdvancementRepository:
    if use_supabase_rest_fallback() and supabase_rest_configured():
        return ResilientAdvancementRepository()
    return InMemoryAdvancementRepository()
