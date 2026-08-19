"""SQLAlchemy model for public.audit_logs."""

from sqlalchemy import Column, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.models.base import Base


class AuditLog(Base):
    """Immutable event log for entity changes."""

    __tablename__ = "audit_logs"
    __table_args__ = {"schema": "public"}

    id = Column(UUID(as_uuid=True), primary_key=True)
    entity_type = Column(Text, nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(Text, nullable=False)
    performed_by = Column(UUID(as_uuid=True), ForeignKey("public.users.id"))
    old_values = Column(JSONB)
    new_values = Column(JSONB)
    timestamp = Column(DateTime(timezone=True), nullable=False)
