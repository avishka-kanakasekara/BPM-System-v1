"""Deterministic duration/KPI/bottleneck math. No LLM. No invented timestamps."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from app.agents.agent4_orchestrator.constants import ExceptionStatus, WorkflowStage
from app.agents.agent4_orchestrator.workflow_plan.constants import WorkflowStepStatus, WorkflowStepType
from app.monitoring.records import MonitoringProcess, MonitoringStep
from app.monitoring.schemas import (
    BottleneckCandidate,
    ExceptionAnalytics,
    KpiReport,
    StepDuration,
    TimelineEvent,
)

_Q = Decimal("0.0001")
ACTIVE_STAGES = {
    WorkflowStage.DRAFT.value,
    WorkflowStage.DISCOVERING.value,
    WorkflowStage.RESOURCE_PLANNING.value,
    WorkflowStage.RISK_REVIEW.value,
    WorkflowStage.AWAITING_HUMAN_APPROVAL.value,
    WorkflowStage.WORKFLOW_EXECUTION.value,
    WorkflowStage.INVOICE_MATCHING.value,
}
HUMAN_WAIT_TYPES = {
    WorkflowStepType.APPROVAL.value,
    WorkflowStepType.HUMAN_TASK.value,
}


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        from datetime import UTC

        return value.replace(tzinfo=UTC)
    return value


def _seconds(start: datetime | None, end: datetime | None) -> Decimal | None:
    start = _aware(start)
    end = _aware(end)
    if start is None or end is None:
        return None
    delta = (end - start).total_seconds()
    if delta < 0:
        return None
    return Decimal(str(delta)).quantize(_Q, rounding=ROUND_HALF_UP)


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    total = sum(values, Decimal("0"))
    return (total / Decimal(len(values))).quantize(_Q, rounding=ROUND_HALF_UP)


def _rate(numerator: int, denominator: int) -> Decimal | None:
    if denominator <= 0:
        return None
    return (Decimal(numerator) / Decimal(denominator)).quantize(_Q, rounding=ROUND_HALF_UP)


def in_window(moment: datetime | None, start: datetime | None, end: datetime | None) -> bool:
    if moment is None:
        return start is None and end is None
    moment = _aware(moment)
    start = _aware(start)
    end = _aware(end)
    if start is not None and moment < start:
        return False
    if end is not None and moment > end:
        return False
    return True


def step_duration(step: MonitoringStep) -> StepDuration:
    duration = _seconds(step.started_at, step.ended_at)
    wait = _seconds(step.waiting_started_at, step.waiting_ended_at)
    human_wait = wait if step.step_type in HUMAN_WAIT_TYPES or step.approval_required else None
    minutes = None if duration is None else (duration / Decimal("60")).quantize(_Q, rounding=ROUND_HALF_UP)
    return StepDuration(
        workflow_step_id=step.workflow_step_id,
        name=step.name,
        step_type=step.step_type,
        status=step.status,
        start_time=step.started_at,
        end_time=step.ended_at,
        duration_seconds=duration,
        duration_minutes=minutes,
        waiting_duration_seconds=wait,
        human_wait_seconds=human_wait,
        failure_count=step.failure_count,
        exception_count=step.exception_count,
    )


def build_timeline(process: MonitoringProcess) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []

    def add(
        event_type: str,
        timestamp: datetime | None,
        *,
        actor: str | None = None,
        status: str | None = None,
        step_id: UUID | None = None,
        evidence_ref: str | None = None,
    ) -> None:
        if timestamp is None:
            return
        events.append(
            TimelineEvent(
                process_id=process.process_id,
                workflow_plan_id=process.workflow_plan_id,
                workflow_step_id=step_id,
                event_type=event_type,
                timestamp=_aware(timestamp) or timestamp,
                actor=actor,
                status=status,
                trace_id=process.trace_id,
                evidence_ref=evidence_ref,
            )
        )

    add("process_created", process.created_at, actor="system", status=process.status)

    for custom in process.events:
        add(
            custom.event_type,
            custom.timestamp,
            actor=custom.actor,
            status=custom.status,
            step_id=custom.workflow_step_id,
            evidence_ref=custom.evidence_ref,
        )

    for approval in process.approvals:
        add(
            "human_approval_requested",
            approval.requested_at,
            actor="human",
            status=approval.status,
            step_id=approval.workflow_step_id,
        )
        if approval.decided_at is not None:
            add(
                "human_approval_completed",
                approval.decided_at,
                actor="human",
                status=approval.status,
                step_id=approval.workflow_step_id,
            )

    for step in process.steps:
        add("workflow_step_started", step.started_at, actor="agent2_execution", status=step.status, step_id=step.workflow_step_id)
        if step.status == WorkflowStepStatus.COMPLETED.value:
            add("workflow_step_completed", step.ended_at, actor="agent2_execution", status=step.status, step_id=step.workflow_step_id)
        elif step.status == WorkflowStepStatus.FAILED.value:
            add("workflow_step_failed", step.ended_at, actor="agent2_execution", status=step.status, step_id=step.workflow_step_id)
        if "invoice" in (step.name or "").lower() or (step.step_key or "").lower().find("invoice") >= 0:
            add("invoice_matching_started", step.started_at, actor="agent4_orchestrator", step_id=step.workflow_step_id)
            if step.status == WorkflowStepStatus.COMPLETED.value:
                add("invoice_matching_completed", step.ended_at, actor="agent4_orchestrator", step_id=step.workflow_step_id)

    for exc in process.exceptions:
        add(
            "exception_created",
            exc.created_at,
            actor="agent4_orchestrator",
            status=exc.status,
            step_id=exc.workflow_step_id,
            evidence_ref=exc.code,
        )
        if exc.resolved_at is not None:
            add(
                "exception_resolved",
                exc.resolved_at,
                actor="human",
                status=exc.status,
                step_id=exc.workflow_step_id,
                evidence_ref=exc.code,
            )

    stage = (process.current_stage or "").upper()
    if stage == WorkflowStage.COMPLETED.value:
        add("process_completed", process.completed_at, actor="agent4_orchestrator", status=stage)

    events.sort(key=lambda item: item.timestamp)
    return events


def exception_analytics(processes: list[MonitoringProcess]) -> ExceptionAnalytics:
    exceptions = [item for process in processes for item in process.exceptions]
    by_code: Counter[str] = Counter()
    by_step: Counter[str] = Counter()
    open_count = 0
    resolved = 0
    for item in exceptions:
        by_code[item.code] += 1
        if item.workflow_step_id is not None:
            by_step[str(item.workflow_step_id)] += 1
        if item.status in {ExceptionStatus.RESOLVED.value, ExceptionStatus.IGNORED.value}:
            resolved += 1
        elif item.status in {ExceptionStatus.OPEN.value, ExceptionStatus.IN_PROGRESS.value}:
            open_count += 1
    most = by_code.most_common(1)[0][0] if by_code else None
    return ExceptionAnalytics(
        total_exceptions=len(exceptions),
        open_exceptions=open_count,
        resolved_exceptions=resolved,
        exceptions_by_code=dict(by_code),
        exceptions_by_workflow_step=dict(by_step),
        exception_rate_per_process=_rate(len(exceptions), len(processes)),
        most_frequent_exception=most,
    )


def rank_bottlenecks(processes: list[MonitoringProcess], *, top_k: int = 5) -> list[BottleneckCandidate]:
    grouped: dict[UUID, dict[str, object]] = {}
    for process in processes:
        for step in process.steps:
            bucket = grouped.setdefault(
                step.workflow_step_id,
                {
                    "name": step.name,
                    "step_type": step.step_type,
                    "durations": [],
                    "waits": [],
                    "failures": 0,
                    "exceptions": 0,
                },
            )
            duration = _seconds(step.started_at, step.ended_at)
            wait = _seconds(step.waiting_started_at, step.waiting_ended_at)
            if duration is not None:
                bucket["durations"].append(duration)  # type: ignore[attr-defined]
            if wait is not None:
                bucket["waits"].append(wait)  # type: ignore[attr-defined]
            bucket["failures"] = int(bucket["failures"]) + int(step.failure_count)
            bucket["exceptions"] = int(bucket["exceptions"]) + int(step.exception_count)

    if not grouped:
        return []

    rows: list[BottleneckCandidate] = []
    for step_id, bucket in grouped.items():
        rows.append(
            BottleneckCandidate(
                workflow_step_id=step_id,
                step=str(bucket["name"]),
                step_type=str(bucket["step_type"]),
                average_duration_seconds=_mean(list(bucket["durations"])),  # type: ignore[arg-type]
                average_wait_seconds=_mean(list(bucket["waits"])),  # type: ignore[arg-type]
                failure_count=int(bucket["failures"]),
                exception_count=int(bucket["exceptions"]),
            )
        )

    max_duration = max((row.average_duration_seconds or Decimal("-1") for row in rows), default=Decimal("-1"))
    max_wait = max((row.average_wait_seconds or Decimal("-1") for row in rows), default=Decimal("-1"))
    max_fail = max((row.failure_count for row in rows), default=0)
    max_exc = max((row.exception_count for row in rows), default=0)

    for row in rows:
        reasons: list[str] = []
        if row.average_duration_seconds is not None and row.average_duration_seconds == max_duration and max_duration >= 0:
            reasons.append("highest_average_duration")
        if row.average_wait_seconds is not None and row.average_wait_seconds == max_wait and max_wait >= 0:
            reasons.append("highest_average_wait_time")
        if max_fail > 0 and row.failure_count == max_fail:
            reasons.append("highest_failure_count")
        if max_exc > 0 and row.exception_count == max_exc:
            reasons.append("highest_exception_count")
        row.reason = reasons

    ranked = [row for row in rows if row.reason]
    ranked.sort(
        key=lambda row: (
            row.average_wait_seconds or Decimal("0"),
            row.average_duration_seconds or Decimal("0"),
            row.failure_count,
            row.exception_count,
        ),
        reverse=True,
    )
    return ranked[:top_k]


def calculate_kpis(
    tenant_id: UUID,
    processes: list[MonitoringProcess],
    *,
    process_id: UUID | None = None,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> KpiReport:
    scoped = [
        process
        for process in processes
        if process.tenant_id == tenant_id
        and (process_id is None or process.process_id == process_id)
        and in_window(process.created_at, window_start, window_end)
    ]
    if not scoped:
        return KpiReport(
            tenant_id=tenant_id,
            process_id=process_id,
            window_start=window_start,
            window_end=window_end,
            window_convention="explicit_start_end_or_all_persisted_records",
            insufficient_evidence=True,
        )

    completed = [p for p in scoped if (p.current_stage or "").upper() == WorkflowStage.COMPLETED.value]
    exceptioned = [p for p in scoped if (p.current_stage or "").upper() == WorkflowStage.EXCEPTION.value]
    active = [p for p in scoped if (p.current_stage or "").upper() in ACTIVE_STAGES]

    completion_times = [_seconds(p.created_at, p.completed_at) for p in completed]
    completion_times = [item for item in completion_times if item is not None]

    step_durations: list[Decimal] = []
    waits: list[Decimal] = []
    successes = 0
    failures = 0
    for process in scoped:
        for step in process.steps:
            duration = _seconds(step.started_at, step.ended_at)
            if duration is not None:
                step_durations.append(duration)
            wait = _seconds(step.waiting_started_at, step.waiting_ended_at)
            if wait is not None and (step.step_type in HUMAN_WAIT_TYPES or step.approval_required):
                waits.append(wait)
            if step.status == WorkflowStepStatus.COMPLETED.value:
                successes += 1
            if step.status in {WorkflowStepStatus.FAILED.value, WorkflowStepStatus.EXCEPTION.value}:
                failures += 1
            elif step.failure_count > 0:
                failures += step.failure_count

    analytics = exception_analytics(scoped)
    bottlenecks = rank_bottlenecks(scoped)
    terminal_steps = successes + failures
    return KpiReport(
        tenant_id=tenant_id,
        process_id=process_id,
        window_start=window_start,
        window_end=window_end,
        window_convention="explicit_start_end_or_all_persisted_records",
        total_processes=len(scoped),
        completed_processes=len(completed),
        exception_processes=len(exceptioned),
        active_processes=len(active),
        completion_rate=_rate(len(completed), len(scoped)),
        exception_rate=_rate(len(exceptioned), len(scoped)),
        average_completion_time_seconds=_mean(completion_times),
        average_step_duration_seconds=_mean(step_durations),
        average_human_wait_time_seconds=_mean(waits),
        workflow_step_success_rate=_rate(successes, terminal_steps),
        workflow_step_failure_rate=_rate(failures, terminal_steps),
        total_exceptions=analytics.total_exceptions,
        exceptions_by_code=analytics.exceptions_by_code,
        bottleneck_steps=bottlenecks,
        insufficient_evidence=False,
    )
