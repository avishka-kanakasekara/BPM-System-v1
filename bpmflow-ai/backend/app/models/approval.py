"""SQLAlchemy model for public.approval_requests."""

from sqlalchemy import Column, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class ApprovalRequest(Base):
    """Agent 4 human approval gate record."""

    __tablename__ = "approval_requests"
    __table_args__ = {"schema": "public"}

    id = Column(UUID(as_uuid=True), primary_key=True)
    process_id = Column(
        UUID(as_uuid=True),
        ForeignKey("public.processes.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("public.tasks.id", ondelete="SET NULL"),
    )
    requested_by = Column(
        UUID(as_uuid=True),
        ForeignKey("public.users.id", ondelete="SET NULL"),
    )
    approver_id = Column(
        UUID(as_uuid=True),
        ForeignKey("public.users.id", ondelete="SET NULL"),
    )
    status = Column(Text, nullable=False, default="PENDING")
    risk_level = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)
    decision = Column(Text)
    comments = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False)
    decided_at = Column(DateTime(timezone=True))
