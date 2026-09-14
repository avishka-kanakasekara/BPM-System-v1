"""Observational monitoring service. Never mutates workflow state."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.monitoring.analytics import (
    build_timeline,
    calculate_kpis,
    exception_analytics,
    rank_bottlenecks,
    step_duration,
)
from app.monitoring.records import MonitoringProcess
from app.monitoring.schemas import (
    BottleneckCandidate,
    ExceptionAnalytics,
    KpiReport,
    ProcessMonitoringReport,
    StepDuration,
    TimelineEvent,
)
from app.monitoring.store import MonitoringStore, get_monitoring_store


class MonitoringService:
    def __init__(self, store: MonitoringStore | None = None) -> None:
        self._store = store or get_monitoring_store()

    def upsert_process(self, record: MonitoringProcess) -> MonitoringProcess:
        return self._store.upsert_process(record)

    def require_process(self, tenant_id: UUID, process_id: UUID) -> MonitoringProcess:
        record = self._store.get_process(tenant_id, process_id)
        if record is None:
            raise ProcessMonitoringNotFoundError(process_id)
        return record

    def timeline(self, tenant_id: UUID, process_id: UUID) -> list[TimelineEvent]:
        return build_timeline(self.require_process(tenant_id, process_id))

    def step_durations(self, tenant_id: UUID, process_id: UUID) -> list[StepDuration]:
        process = self.require_process(tenant_id, process_id)
        return [step_duration(step) for step in process.steps]

    def kpis(
        self,
        tenant_id: UUID,
        *,
        process_id: UUID | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> KpiReport:
        processes = self._store.list_processes(tenant_id)
        return calculate_kpis(
            tenant_id,
            processes,
            process_id=process_id,
            window_start=window_start,
            window_end=window_end,
        )

    def bottlenecks(self, tenant_id: UUID, process_id: UUID | None = None) -> list[BottleneckCandidate]:
        processes = self._store.list_processes(tenant_id)
        if process_id is not None:
            processes = [item for item in processes if item.process_id == process_id]
        return rank_bottlenecks(processes)

    def exception_analytics(
        self, tenant_id: UUID, process_id: UUID | None = None
    ) -> ExceptionAnalytics:
        processes = self._store.list_processes(tenant_id)
        if process_id is not None:
            processes = [item for item in processes if item.process_id == process_id]
        return exception_analytics(processes)

    def report(self, tenant_id: UUID, process_id: UUID) -> ProcessMonitoringReport:
        process = self.require_process(tenant_id, process_id)
        durations = [step_duration(step) for step in process.steps]
        from app.monitoring.analytics import _seconds

        duration = _seconds(process.created_at, process.completed_at)
        return ProcessMonitoringReport(
            process_id=process.process_id,
            tenant_id=process.tenant_id,
            state=process.current_stage,
            status=process.status,
            started_at=process.created_at,
            completed_at=process.completed_at,
            duration_seconds=duration,
            timeline=build_timeline(process),
            steps=durations,
            exceptions=[
                {
                    "exception_id": str(item.exception_id),
                    "code": item.code,
                    "status": item.status,
                    "created_at": item.created_at.isoformat(),
                    "resolved_at": None if item.resolved_at is None else item.resolved_at.isoformat(),
                    "workflow_step_id": None
                    if item.workflow_step_id is None
                    else str(item.workflow_step_id),
                }
                for item in process.exceptions
            ],
            kpis=calculate_kpis(tenant_id, [process], process_id=process_id),
            bottlenecks=rank_bottlenecks([process]),
            exception_analytics=exception_analytics([process]),
        )


class ProcessMonitoringNotFoundError(LookupError):
    def __init__(self, process_id: UUID) -> None:
        super().__init__(f"Process {process_id} not found for tenant")
        self.process_id = process_id
