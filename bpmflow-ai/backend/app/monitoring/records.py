"""Persisted monitoring facts. Missing timestamps stay None — never invented."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class MonitoringEvent:
    event_type: str
    timestamp: datetime
    actor: str | None = None
    status: str | None = None
    workflow_plan_id: UUID | None = None
    workflow_step_id: UUID | None = None
    trace_id: str | None = None
    evidence_ref: str | None = None


@dataclass
class MonitoringStep:
    workflow_step_id: UUID
    name: str
    step_type: str
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    waiting_started_at: datetime | None = None
    waiting_ended_at: datetime | None = None
    approval_required: bool = False
    depends_on_step_keys: list[str] = field(default_factory=list)
    step_key: str | None = None
    failure_count: int = 0
    exception_count: int = 0


@dataclass
class MonitoringException:
    exception_id: UUID
    code: str
    status: str
    created_at: datetime
    resolved_at: datetime | None = None
    workflow_step_id: UUID | None = None
    title: str | None = None


@dataclass
class MonitoringApproval:
    approval_id: UUID
    status: str
    requested_at: datetime
    decided_at: datetime | None = None
    workflow_step_id: UUID | None = None


@dataclass
class MonitoringProcess:
    process_id: UUID
    tenant_id: UUID
    name: str
    current_stage: str
    status: str
    created_at: datetime
    completed_at: datetime | None = None
    trace_id: str | None = None
    workflow_plan_id: UUID | None = None
    purchase_request_id: str | None = None
    steps: list[MonitoringStep] = field(default_factory=list)
    exceptions: list[MonitoringException] = field(default_factory=list)
    approvals: list[MonitoringApproval] = field(default_factory=list)
    events: list[MonitoringEvent] = field(default_factory=list)
