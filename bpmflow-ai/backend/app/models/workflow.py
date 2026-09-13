"""Agent 4 WorkflowPlan / WorkflowStep persistence (Phase 4 definition only)."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base

JsonDict = JSON().with_variant(JSONB(), "postgresql")
JsonList = JSON().with_variant(JSONB(), "postgresql")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class WorkflowPlan(Base):
    """Persistent workflow definition owned by Agent 4."""

    __tablename__ = "workflow_plans"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="workflow_plans_tenant_id_unique"),
        UniqueConstraint(
            "tenant_id", "process_id", "version",
            name="workflow_plans_tenant_process_version_unique",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    process_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("processes.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="DRAFT")
    created_by_agent: Mapped[str] = mapped_column(Text, nullable=False, default="agent4")
    source_process_context_schema_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_process_context_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class WorkflowStep(Base):
    """Ordered step inside a WorkflowPlan. Creating a row is not execution."""

    __tablename__ = "workflow_steps"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="workflow_steps_tenant_id_unique"),
        UniqueConstraint(
            "tenant_id", "workflow_plan_id", "step_key",
            name="workflow_steps_plan_key_unique",
        ),
        UniqueConstraint(
            "tenant_id", "workflow_plan_id", "sequence",
            name="workflow_steps_plan_sequence_unique",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    workflow_plan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workflow_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_key: Mapped[str] = mapped_column(String(128), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    step_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="PENDING")
    responsible_employee_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    responsible_resource_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    responsible_role_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    responsible_department_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    assignment_unresolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    unresolved_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_tool_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    inputs: Mapped[dict] = mapped_column(JsonDict, nullable=False, default=dict)
    expected_outputs: Mapped[dict] = mapped_column(JsonDict, nullable=False, default=dict)
    evidence_refs: Mapped[list] = mapped_column(JsonList, nullable=False, default=list)
    policy_refs: Mapped[list] = mapped_column(JsonList, nullable=False, default=list)
    risk_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    recipient_employee_ids: Mapped[list] = mapped_column(JsonList, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class WorkflowStepDependency(Base):
    """Same-plan dependency edge using stable step UUIDs."""

    __tablename__ = "workflow_step_dependencies"

    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    step_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workflow_steps.id", ondelete="CASCADE"),
        primary_key=True,
    )
    depends_on_step_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workflow_steps.id", ondelete="CASCADE"),
        primary_key=True,
    )
    workflow_plan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workflow_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
