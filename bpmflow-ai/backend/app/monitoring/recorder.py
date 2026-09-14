"""Record observational monitoring facts from live execution. Never invent timestamps."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.monitoring.records import (
    MonitoringEvent,
    MonitoringException,
    MonitoringProcess,
    MonitoringStep,
)
from app.monitoring.store import get_monitoring_store


def _now() -> datetime:
    return datetime.now(UTC)


def record_process_snapshot(
    *,
    process_id: UUID,
    tenant_id: UUID,
    name: str,
    current_stage: str,
    status: str,
    created_at: datetime | None = None,
    completed_at: datetime | None = None,
    workflow_plan_id: UUID | None = None,
    purchase_request_id: str | None = None,
    trace_id: str | None = None,
    event_type: str | None = None,
    actor: str | None = None,
) -> MonitoringProcess:
    store = get_monitoring_store()
    existing = store.get_process(tenant_id, process_id)
    events = list(existing.events) if existing else []
    if event_type:
        events.append(
            MonitoringEvent(
                event_type=event_type,
                timestamp=_now(),
                actor=actor,
                status=status,
                workflow_plan_id=workflow_plan_id,
            )
        )
    record = MonitoringProcess(
        process_id=process_id,
        tenant_id=tenant_id,
        name=name,
        current_stage=current_stage,
        status=status,
        created_at=created_at or (existing.created_at if existing else _now()),
        completed_at=completed_at if completed_at is not None else (existing.completed_at if existing else None),
        trace_id=trace_id or (existing.trace_id if existing else None),
        workflow_plan_id=workflow_plan_id or (existing.workflow_plan_id if existing else None),
        purchase_request_id=purchase_request_id
        or (existing.purchase_request_id if existing else None),
        steps=list(existing.steps) if existing else [],
        exceptions=list(existing.exceptions) if existing else [],
        approvals=list(existing.approvals) if existing else [],
        events=events,
    )
    return store.upsert_process(record)


def record_step_execution(
    *,
    process_id: UUID,
    tenant_id: UUID,
    workflow_plan_id: UUID,
    workflow_step_id: UUID,
    name: str,
    step_type: str,
    status: str,
    started_at: datetime,
    ended_at: datetime | None,
    step_key: str | None = None,
    depends_on_step_keys: list[str] | None = None,
    approval_required: bool = False,
    failure_count: int = 0,
    exception_count: int = 0,
    actor: str = "agent2_execution",
) -> None:
    store = get_monitoring_store()
    existing = store.get_process(tenant_id, process_id)
    if existing is None:
        existing = record_process_snapshot(
            process_id=process_id,
            tenant_id=tenant_id,
            name=str(process_id),
            current_stage="WORKFLOW_EXECUTION",
            status="ACTIVE",
            workflow_plan_id=workflow_plan_id,
        )
    steps = [item for item in existing.steps if item.workflow_step_id != workflow_step_id]
    steps.append(
        MonitoringStep(
            workflow_step_id=workflow_step_id,
            name=name,
            step_type=step_type,
            status=status,
            started_at=started_at,
            ended_at=ended_at,
            approval_required=approval_required,
            waiting_started_at=started_at if approval_required else None,
            waiting_ended_at=ended_at if approval_required else None,
            depends_on_step_keys=list(depends_on_step_keys or []),
            step_key=step_key,
            failure_count=failure_count,
            exception_count=exception_count,
        )
    )
    event_type = "workflow_step_completed"
    if status in {"FAILED", "EXCEPTION"}:
        event_type = "workflow_step_failed"
    events = list(existing.events)
    events.append(
        MonitoringEvent(
            event_type="workflow_step_started",
            timestamp=started_at,
            actor=actor,
            status=status,
            workflow_plan_id=workflow_plan_id,
            workflow_step_id=workflow_step_id,
        )
    )
    if ended_at is not None:
        events.append(
            MonitoringEvent(
                event_type=event_type,
                timestamp=ended_at,
                actor=actor,
                status=status,
                workflow_plan_id=workflow_plan_id,
                workflow_step_id=workflow_step_id,
            )
        )
    store.upsert_process(
        MonitoringProcess(
            process_id=existing.process_id,
            tenant_id=existing.tenant_id,
            name=existing.name,
            current_stage=existing.current_stage,
            status=existing.status,
            created_at=existing.created_at,
            completed_at=existing.completed_at,
            trace_id=existing.trace_id,
            workflow_plan_id=workflow_plan_id,
            purchase_request_id=existing.purchase_request_id,
            steps=steps,
            exceptions=existing.exceptions,
            approvals=existing.approvals,
            events=events,
        )
    )


def record_exception(
    *,
    process_id: UUID,
    tenant_id: UUID,
    exception_id: UUID,
    code: str,
    status: str,
    created_at: datetime | None = None,
    workflow_step_id: UUID | None = None,
    title: str | None = None,
) -> None:
    store = get_monitoring_store()
    existing = store.get_process(tenant_id, process_id)
    if existing is None:
        return
    exceptions = list(existing.exceptions)
    exceptions.append(
        MonitoringException(
            exception_id=exception_id,
            code=code,
            status=status,
            created_at=created_at or _now(),
            workflow_step_id=workflow_step_id,
            title=title,
        )
    )
    events = list(existing.events)
    events.append(
        MonitoringEvent(
            event_type="exception_created",
            timestamp=created_at or _now(),
            actor="agent4_orchestrator",
            status=status,
            workflow_step_id=workflow_step_id,
            evidence_ref=code,
        )
    )
    store.upsert_process(
        MonitoringProcess(
            process_id=existing.process_id,
            tenant_id=existing.tenant_id,
            name=existing.name,
            current_stage=existing.current_stage,
            status=existing.status,
            created_at=existing.created_at,
            completed_at=existing.completed_at,
            trace_id=existing.trace_id,
            workflow_plan_id=existing.workflow_plan_id,
            purchase_request_id=existing.purchase_request_id,
            steps=existing.steps,
            exceptions=exceptions,
            approvals=existing.approvals,
            events=events,
        )
    )
