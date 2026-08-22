"""SQLAlchemy model for public.exceptions."""

from sqlalchemy import Column, Text, DateTime, ForeignKey
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
    severity = Column(Text, nullable=False)
    type = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="open")
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("public.users.id"))
    resolution_notes = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True))
