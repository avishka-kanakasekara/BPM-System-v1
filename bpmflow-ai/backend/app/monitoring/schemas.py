"""Phase 10 monitoring, KPI, and TO-BE recommendation schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

RecommendationStatus = Literal["PROPOSED", "ACCEPTED", "REJECTED", "IMPLEMENTED", "NOT_ALLOWED"]
ReviewDecision = Literal["ACCEPTED", "REJECTED"]


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    process_id: UUID
    workflow_plan_id: UUID | None = None
    workflow_step_id: UUID | None = None
    event_type: str
    timestamp: datetime
    actor: str | None = None
    status: str | None = None
    trace_id: str | None = None
    evidence_ref: str | None = None


class StepDuration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_step_id: UUID
    name: str
    step_type: str | None = None
    status: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_seconds: Decimal | None = None
    duration_minutes: Decimal | None = None
    waiting_duration_seconds: Decimal | None = None
    human_wait_seconds: Decimal | None = None
    failure_count: int = 0
    exception_count: int = 0


class BottleneckCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_step_id: UUID | None = None
    step: str
    step_type: str | None = None
    average_duration_seconds: Decimal | None = None
    average_wait_seconds: Decimal | None = None
    failure_count: int = 0
    exception_count: int = 0
    reason: list[str] = Field(default_factory=list)


class ExceptionAnalytics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_exceptions: int = 0
    open_exceptions: int = 0
    resolved_exceptions: int = 0
    exceptions_by_code: dict[str, int] = Field(default_factory=dict)
    exceptions_by_workflow_step: dict[str, int] = Field(default_factory=dict)
    exception_rate_per_process: Decimal | None = None
    most_frequent_exception: str | None = None


class KpiReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    process_id: UUID | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    window_convention: str = "all_persisted_records"
    total_processes: int = 0
    completed_processes: int = 0
    exception_processes: int = 0
    active_processes: int = 0
    completion_rate: Decimal | None = None
    exception_rate: Decimal | None = None
    average_completion_time_seconds: Decimal | None = None
    average_step_duration_seconds: Decimal | None = None
    average_human_wait_time_seconds: Decimal | None = None
    workflow_step_success_rate: Decimal | None = None
    workflow_step_failure_rate: Decimal | None = None
    total_exceptions: int = 0
    exceptions_by_code: dict[str, int] = Field(default_factory=dict)
    bottleneck_steps: list[BottleneckCandidate] = Field(default_factory=list)
    insufficient_evidence: bool = False


class ProcessMonitoringReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    process_id: UUID
    tenant_id: UUID
    state: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: Decimal | None = None
    timeline: list[TimelineEvent] = Field(default_factory=list)
    steps: list[StepDuration] = Field(default_factory=list)
    exceptions: list[dict[str, Any]] = Field(default_factory=list)
    kpis: KpiReport
    bottlenecks: list[BottleneckCandidate] = Field(default_factory=list)
    exception_analytics: ExceptionAnalytics


class RecommendationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_step_id: UUID | None = None
    field: str
    value: Any
    source: str


class TobeRecommendationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    process_id: UUID | None = None
    workflow_plan_id: UUID | None = None
    recommendation_type: str
    title: str
    description: str
    reason: str
    evidence: list[RecommendationEvidence] = Field(default_factory=list)
    kpi_snapshot: dict[str, Any] = Field(default_factory=dict)
    expected_benefit: str | None = None
    risk: str | None = None
    confidence: Decimal | None = None
    status: RecommendationStatus = "PROPOSED"
    fingerprint: str
    created_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: UUID | None = None
    activates_workflow: bool = False
    policy_status: str | None = None


class RecommendationReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ReviewDecision
    comment: str | None = None
