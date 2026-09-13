"""SQLAlchemy model for public.exceptions."""

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class ProcessException(Base):
    """BPM exception/issue row. Table name is exceptions."""

    __tablename__ = "exceptions"
    __table_args__ = {"schema": "public"}

    id = Column(UUID(as_uuid=True), primary_key=True)
    task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("public.tasks.id", ondelete="CASCADE"),
    )
    process_id = Column(
        UUID(as_uuid=True),
        ForeignKey("public.processes.id", ondelete="CASCADE"),
    )
    tenant_id = Column(UUID(as_uuid=True))
    workflow_plan_id = Column(UUID(as_uuid=True))
    workflow_step_id = Column(UUID(as_uuid=True))
    exception_code = Column(Text)
    title = Column(Text)
    severity = Column(Text, nullable=False)
    type = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="open")
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("public.users.id"))
    assigned_employee_id = Column(UUID(as_uuid=True))
    resolved_by_employee_id = Column(UUID(as_uuid=True))
    source_agent = Column(Text)
    source_operation = Column(Text)
    evidence_refs = Column(JSON, default=list)
    details = Column(JSON, default=dict)
    resolution_notes = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True))
    resolved_at = Column(DateTime(timezone=True))
