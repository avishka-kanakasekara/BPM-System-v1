"""Audit ORM models.

Two tables, two classes:
- IngestionAuditLog → public.ingestion_audit_logs (Agent 1 document ingest)
- AuditLog → public.audit_logs (BPM entity change log used by Agents 3/4)
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
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
    """Immutable BPM event log for entity changes and Agent 2 guard decisions.

    Agent 3/4 rows fill entity_type/entity_id/old_values/new_values.
    Agent 2 tool-guard rows fill actor/agent/allowed/reason/payload
    (migration 0005); entity_id is nullable for those rows.
    """

    __tablename__ = "audit_logs"
    __table_args__ = {"schema": "public"}

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    entity_type = Column(Text, nullable=False)
    entity_id = Column(Uuid(as_uuid=True), nullable=True)
    action = Column(Text, nullable=False)
    performed_by = Column(Uuid(as_uuid=True), ForeignKey("public.users.id"))
    old_values = Column(JsonDict)
    new_values = Column(JsonDict)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    # Agent 2 tool-guard decision columns (migration 0005).
    actor = Column(Text, nullable=True)
    agent = Column(Text, nullable=True)
    allowed = Column(Boolean, nullable=True)
    reason = Column(Text, nullable=True)
    payload = Column(JsonDict, nullable=True)
