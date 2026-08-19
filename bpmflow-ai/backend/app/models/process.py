"""SQLAlchemy model for public.processes."""

from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class Process(Base):
    """BPM process record, including Agent 4 current_stage."""

    __tablename__ = "processes"
    __table_args__ = {"schema": "public"}

    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(Text, nullable=False)
    description = Column(Text)
    process_type = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="draft")
    version = Column(Integer, default=1)
    created_by = Column(UUID(as_uuid=True), ForeignKey("public.users.id"))
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    current_stage = Column(Text, nullable=False, default="DRAFT")
