"""Audit ORM models.

Two tables, two classes:
- IngestionAuditLog → public.ingestion_audit_logs (Agent 1 document ingest)
- AuditLog → public.audit_logs (BPM entity change log used by Agents 3/4)
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base as CoreBase
from app.models.base import Base

JsonDict = JSON().with_variant(JSONB(), "postgresql")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IngestionAuditLog(CoreBase):
    """Agent 1 ingest attempts. Not the BPM audit_logs table."""

    __tablename__ = "ingestion_audit_logs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    file_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    detail_json: Mapped[dict] = mapped_column(JsonDict, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
    )


class AuditLog(Base):
    """Immutable BPM event log for entity changes."""

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
