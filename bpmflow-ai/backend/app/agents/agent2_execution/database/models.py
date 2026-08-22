"""
Agent 2 — ORM models on the shared BPMFlow data layer.

After integration (migration 0005) Agent 2 no longer owns private
process_instances / tasks / agent_messages / audit_logs tables. It maps onto
the canonical shared tables:

- ProcessInstance  -> app.models.process.Process        (table: processes)
- Task             -> app.models.process.ProcessTask    (table: tasks)
- AuditLog         -> app.models.audit.AuditLog         (table: audit_logs)
- agent messages   -> app.models.agent_message.AgentMessageRecord

The eleven Agent 2-owned tables below keep their original shapes, with
foreign keys re-pointed at the canonical processes/tasks tables. They live on
the same declarative Base as the canonical models so create_all builds one
coherent schema.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base

# Canonical shared models re-exported under Agent 2's historical names.
from app.models.agent_message import AgentMessageRecord
from app.models.audit import AuditLog  # noqa: F401  (re-export)
from app.models.process import Process, ProcessTask

ProcessInstance = Process
Task = ProcessTask
AgentMessage = AgentMessageRecord


class TimestampMixin:
    """Adds created_at and updated_at columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# 1. execution_plans
# ---------------------------------------------------------------------------

class ExecutionPlan(TimestampMixin, Base):
    __tablename__ = "execution_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    process_instance_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("processes.id"), nullable=False
    )
    plan_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="DRAFT")
    plan_json: Mapped[Optional[dict]] = mapped_column(JSON)
    reasoning: Mapped[Optional[str]] = mapped_column(Text)
    approved_by: Mapped[Optional[str]] = mapped_column(String(255))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------------------
# 2. execution_attempts
# ---------------------------------------------------------------------------

class ExecutionAttempt(TimestampMixin, Base):
    __tablename__ = "execution_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="RUNNING")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    result_json: Mapped[Optional[dict]] = mapped_column(JSON)
    error_message: Mapped[Optional[str]] = mapped_column(Text)


# ---------------------------------------------------------------------------
# 3. tool_calls
# ---------------------------------------------------------------------------

class ToolCall(TimestampMixin, Base):
    __tablename__ = "tool_calls"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    execution_attempt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("execution_attempts.id"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    parameters_json: Mapped[Optional[dict]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")
    result_json: Mapped[Optional[dict]] = mapped_column(JSON)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)


# ---------------------------------------------------------------------------
# 4. execution_receipts
# ---------------------------------------------------------------------------

class ExecutionReceipt(TimestampMixin, Base):
    __tablename__ = "execution_receipts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    process_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("processes.id"), nullable=False
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id"), nullable=False
    )
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    idempotency_key: Mapped[str] = mapped_column(
        String(500), nullable=False, unique=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="RUNNING")
    result: Mapped[Optional[dict]] = mapped_column(JSON)
    error_type: Mapped[Optional[str]] = mapped_column(String(255))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)

    __table_args__ = (
        Index("ix_execution_receipts_idempotency_key", "idempotency_key", unique=True),
    )


# ---------------------------------------------------------------------------
# 5. workflow_events
# ---------------------------------------------------------------------------

class WorkflowEvent(Base):
    __tablename__ = "workflow_events"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    process_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("processes.id"), nullable=False
    )
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id")
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    actor: Mapped[Optional[str]] = mapped_column(String(255))
    agent: Mapped[Optional[str]] = mapped_column(String(100))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON)
    previous_state: Mapped[Optional[str]] = mapped_column(String(50))
    new_state: Mapped[Optional[str]] = mapped_column(String(50))


# ---------------------------------------------------------------------------
# 6. email_events
# ---------------------------------------------------------------------------

class EmailEvent(TimestampMixin, Base):
    __tablename__ = "email_events"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    execution_receipt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("execution_receipts.id"), nullable=False
    )
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    recipient_role: Mapped[str] = mapped_column(String(100), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    template_name: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="QUEUED")
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[Optional[str]] = mapped_column(Text)


# ---------------------------------------------------------------------------
# 7. failures
# ---------------------------------------------------------------------------

class Failure(TimestampMixin, Base):
    __tablename__ = "failures"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    execution_receipt_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("execution_receipts.id")
    )
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id")
    )
    failure_type: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIUM")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[Optional[str]] = mapped_column(Text)
    resolution_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="OPEN"
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------------------
# 8. retry_attempts
# ---------------------------------------------------------------------------

class RetryAttempt(TimestampMixin, Base):
    __tablename__ = "retry_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    failure_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("failures.id"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy: Mapped[str] = mapped_column(
        String(100), nullable=False, default="EXPONENTIAL_BACKOFF"
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    result_json: Mapped[Optional[dict]] = mapped_column(JSON)
    error_message: Mapped[Optional[str]] = mapped_column(Text)


# ---------------------------------------------------------------------------
# 9. sla_events
# ---------------------------------------------------------------------------

class SLAEvent(TimestampMixin, Base):
    __tablename__ = "sla_events"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    sla_hours: Mapped[float] = mapped_column(Float, nullable=False)
    elapsed_hours: Mapped[float] = mapped_column(Float, nullable=False)
    threshold_percent: Mapped[Optional[float]] = mapped_column(Float)
    notified_roles: Mapped[Optional[dict]] = mapped_column(JSON)
    message: Mapped[Optional[str]] = mapped_column(Text)


# ---------------------------------------------------------------------------
# 10. process_kpis
# ---------------------------------------------------------------------------

class ProcessKPI(TimestampMixin, Base):
    __tablename__ = "process_kpis"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    process_instance_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("processes.id")
    )
    process_type: Mapped[str] = mapped_column(String(100), nullable=False)
    time_window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    time_window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    avg_cycle_time_hours: Mapped[Optional[float]] = mapped_column(Float)
    avg_task_duration_hours: Mapped[Optional[float]] = mapped_column(Float)
    completion_rate: Mapped[Optional[float]] = mapped_column(Float)
    sla_compliance_rate: Mapped[Optional[float]] = mapped_column(Float)
    failure_rate: Mapped[Optional[float]] = mapped_column(Float)
    throughput: Mapped[Optional[int]] = mapped_column(Integer)
    bottleneck_task: Mapped[Optional[str]] = mapped_column(String(255))
    kpi_data_json: Mapped[Optional[dict]] = mapped_column(JSON)


# ---------------------------------------------------------------------------
# 11. optimization_recommendations
# ---------------------------------------------------------------------------

class OptimizationRecommendation(TimestampMixin, Base):
    __tablename__ = "optimization_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    process_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("processes.id"), nullable=False
    )
    recommendation_type: Mapped[str] = mapped_column(String(100), nullable=False)
    problem: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[Optional[dict]] = mapped_column(JSON)
    baseline_metric: Mapped[Optional[float]] = mapped_column(Float)
    predicted_metric: Mapped[Optional[float]] = mapped_column(Float)
    improvement_percent: Mapped[Optional[float]] = mapped_column(Float)
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    risk: Mapped[Optional[str]] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="PENDING_APPROVAL"
    )
    approved_by: Mapped[Optional[str]] = mapped_column(String(255))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
