"""
Agent 2 — SQLAlchemy ORM Models (15 tables)

All tables use snake_case naming, _id suffix for foreign keys,
and created_at / updated_at timestamps where appropriate.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Shared declarative base for all Agent 2 models."""
    pass


# ---------------------------------------------------------------------------
# Helper mixins
# ---------------------------------------------------------------------------

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
# 1. process_instances
# ---------------------------------------------------------------------------

class ProcessInstance(TimestampMixin, Base):
    __tablename__ = "process_instances"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    process_definition_id: Mapped[Optional[str]] = mapped_column(String(255))
    process_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="CREATED"
    )
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default="MEDIUM"
    )
    requester_id: Mapped[Optional[str]] = mapped_column(String(255))
    requester_name: Mapped[Optional[str]] = mapped_column(String(255))
    department: Mapped[Optional[str]] = mapped_column(String(100))
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    tasks: Mapped[list["Task"]] = relationship(back_populates="process_instance")
    execution_plans: Mapped[list["ExecutionPlan"]] = relationship(
        back_populates="process_instance"
    )
    workflow_events: Mapped[list["WorkflowEvent"]] = relationship(
        back_populates="process_instance"
    )
    execution_receipts: Mapped[list["ExecutionReceipt"]] = relationship(
        back_populates="process_instance"
    )
    process_kpis: Mapped[list["ProcessKPI"]] = relationship(
        back_populates="process_instance"
    )
    optimization_recommendations: Mapped[list["OptimizationRecommendation"]] = (
        relationship(back_populates="process_instance")
    )
    agent_messages: Mapped[list["AgentMessage"]] = relationship(
        back_populates="process_instance"
    )


# ---------------------------------------------------------------------------
# 2. tasks
# ---------------------------------------------------------------------------

class Task(TimestampMixin, Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    process_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_instances.id"), nullable=False
    )
    task_definition_id: Mapped[Optional[str]] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    task_type: Mapped[str] = mapped_column(
        String(100), nullable=False, default="MANUAL"
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="PENDING"
    )
    assigned_role: Mapped[Optional[str]] = mapped_column(String(100))
    assigned_to: Mapped[Optional[str]] = mapped_column(String(255))
    sla_hours: Mapped[Optional[float]] = mapped_column(Float)
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default="MEDIUM"
    )
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    result_json: Mapped[Optional[dict]] = mapped_column(JSON)
    sequence_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    process_instance: Mapped["ProcessInstance"] = relationship(
        back_populates="tasks"
    )
    execution_attempts: Mapped[list["ExecutionAttempt"]] = relationship(
        back_populates="task"
    )
    execution_receipts: Mapped[list["ExecutionReceipt"]] = relationship(
        back_populates="task"
    )
    workflow_events: Mapped[list["WorkflowEvent"]] = relationship(
        back_populates="task"
    )
    failures: Mapped[list["Failure"]] = relationship(back_populates="task")
    sla_events: Mapped[list["SLAEvent"]] = relationship(back_populates="task")


# ---------------------------------------------------------------------------
# 3. execution_plans
# ---------------------------------------------------------------------------

class ExecutionPlan(TimestampMixin, Base):
    __tablename__ = "execution_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    process_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_instances.id"), nullable=False
    )
    plan_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="DRAFT"
    )
    plan_json: Mapped[Optional[dict]] = mapped_column(JSON)
    reasoning: Mapped[Optional[str]] = mapped_column(Text)
    approved_by: Mapped[Optional[str]] = mapped_column(String(255))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    process_instance: Mapped["ProcessInstance"] = relationship(
        back_populates="execution_plans"
    )


# ---------------------------------------------------------------------------
# 4. execution_attempts
# ---------------------------------------------------------------------------

class ExecutionAttempt(TimestampMixin, Base):
    __tablename__ = "execution_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="RUNNING"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    result_json: Mapped[Optional[dict]] = mapped_column(JSON)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    task: Mapped["Task"] = relationship(back_populates="execution_attempts")
    tool_calls: Mapped[list["ToolCall"]] = relationship(
        back_populates="execution_attempt"
    )


# ---------------------------------------------------------------------------
# 5. tool_calls
# ---------------------------------------------------------------------------

class ToolCall(TimestampMixin, Base):
    __tablename__ = "tool_calls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    execution_attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("execution_attempts.id"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    parameters_json: Mapped[Optional[dict]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="PENDING"
    )
    result_json: Mapped[Optional[dict]] = mapped_column(JSON)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)

    # Relationships
    execution_attempt: Mapped["ExecutionAttempt"] = relationship(
        back_populates="tool_calls"
    )


# ---------------------------------------------------------------------------
# 6. execution_receipts
# ---------------------------------------------------------------------------

class ExecutionReceipt(TimestampMixin, Base):
    __tablename__ = "execution_receipts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    process_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_instances.id"), nullable=False
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False
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
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="RUNNING"
    )
    result: Mapped[Optional[dict]] = mapped_column(JSON)
    error_type: Mapped[Optional[str]] = mapped_column(String(255))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)

    # Relationships
    process_instance: Mapped["ProcessInstance"] = relationship(
        back_populates="execution_receipts"
    )
    task: Mapped["Task"] = relationship(back_populates="execution_receipts")
    email_events: Mapped[list["EmailEvent"]] = relationship(
        back_populates="execution_receipt"
    )

    __table_args__ = (
        Index("ix_execution_receipts_idempotency_key", "idempotency_key", unique=True),
    )


# ---------------------------------------------------------------------------
# 7. workflow_events
# ---------------------------------------------------------------------------

class WorkflowEvent(Base):
    __tablename__ = "workflow_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    process_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_instances.id"), nullable=False
    )
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id")
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

    # Relationships
    process_instance: Mapped["ProcessInstance"] = relationship(
        back_populates="workflow_events"
    )
    task: Mapped[Optional["Task"]] = relationship(back_populates="workflow_events")


# ---------------------------------------------------------------------------
# 8. email_events
# ---------------------------------------------------------------------------

class EmailEvent(TimestampMixin, Base):
    __tablename__ = "email_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    execution_receipt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("execution_receipts.id"), nullable=False
    )
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    recipient_role: Mapped[str] = mapped_column(String(100), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    template_name: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="QUEUED"
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    execution_receipt: Mapped["ExecutionReceipt"] = relationship(
        back_populates="email_events"
    )


# ---------------------------------------------------------------------------
# 9. failures
# ---------------------------------------------------------------------------

class Failure(TimestampMixin, Base):
    __tablename__ = "failures"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    execution_receipt_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("execution_receipts.id")
    )
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id")
    )
    failure_type: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="MEDIUM"
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[Optional[str]] = mapped_column(Text)
    resolution_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="OPEN"
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    task: Mapped[Optional["Task"]] = relationship(back_populates="failures")
    retry_attempts: Mapped[list["RetryAttempt"]] = relationship(
        back_populates="failure"
    )


# ---------------------------------------------------------------------------
# 10. retry_attempts
# ---------------------------------------------------------------------------

class RetryAttempt(TimestampMixin, Base):
    __tablename__ = "retry_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    failure_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("failures.id"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy: Mapped[str] = mapped_column(
        String(100), nullable=False, default="EXPONENTIAL_BACKOFF"
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="PENDING"
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    result_json: Mapped[Optional[dict]] = mapped_column(JSON)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    failure: Mapped["Failure"] = relationship(back_populates="retry_attempts")


# ---------------------------------------------------------------------------
# 11. sla_events
# ---------------------------------------------------------------------------

class SLAEvent(TimestampMixin, Base):
    __tablename__ = "sla_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # e.g. WARNING, BREACHED, RESOLVED
    sla_hours: Mapped[float] = mapped_column(Float, nullable=False)
    elapsed_hours: Mapped[float] = mapped_column(Float, nullable=False)
    threshold_percent: Mapped[Optional[float]] = mapped_column(Float)
    notified_roles: Mapped[Optional[dict]] = mapped_column(JSON)
    message: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    task: Mapped["Task"] = relationship(back_populates="sla_events")


# ---------------------------------------------------------------------------
# 12. process_kpis
# ---------------------------------------------------------------------------

class ProcessKPI(TimestampMixin, Base):
    __tablename__ = "process_kpis"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    process_instance_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_instances.id")
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

    # Relationships
    process_instance: Mapped[Optional["ProcessInstance"]] = relationship(
        back_populates="process_kpis"
    )


# ---------------------------------------------------------------------------
# 13. optimization_recommendations
# ---------------------------------------------------------------------------

class OptimizationRecommendation(TimestampMixin, Base):
    __tablename__ = "optimization_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    process_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_instances.id"), nullable=False
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

    # Relationships
    process_instance: Mapped["ProcessInstance"] = relationship(
        back_populates="optimization_recommendations"
    )


# ---------------------------------------------------------------------------
# 14. agent_messages
# ---------------------------------------------------------------------------

class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    message_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    process_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("process_instances.id")
    )
    trace_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    sender: Mapped[str] = mapped_column(String(100), nullable=False)
    receiver: Mapped[str] = mapped_column(String(100), nullable=False)
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[Optional[dict]] = mapped_column(JSON)
    evidence_refs: Mapped[Optional[dict]] = mapped_column(JSON)
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="SENT"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    process_instance: Mapped[Optional["ProcessInstance"]] = relationship(
        back_populates="agent_messages"
    )


# ---------------------------------------------------------------------------
# 15. audit_logs
# ---------------------------------------------------------------------------

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    agent: Mapped[Optional[str]] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    payload: Mapped[Optional[dict]] = mapped_column(JSON)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
