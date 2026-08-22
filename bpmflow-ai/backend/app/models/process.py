"""Process, task, and exception rows stored in Supabase.

One Process model for Agent 1 discovery fields and Agent 4 current_stage.
created_by is a UUID without a users FK so Agent 1 can persist without auth.users rows.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base

JsonDict = JSON().with_variant(JSONB(), "postgresql")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Process(Base):
    """BPM process record: discovery payload plus Agent 4 stage."""

    __tablename__ = "processes"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    process_type: Mapped[str] = mapped_column(Text, nullable=False, default="discovered")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    process_json: Mapped[dict] = mapped_column(JsonDict, nullable=False, default=dict)
    overall_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    discovery_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    trace_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    message_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    current_stage: Mapped[str] = mapped_column(Text, nullable=False, default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class ProcessTask(Base):
    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    process_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("processes.id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    assigned_to: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    priority: Mapped[str | None] = mapped_column(Text, default="medium")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    actor: Mapped[str | None] = mapped_column(Text, nullable=True)
    system: Mapped[str | None] = mapped_column(Text, nullable=True)
    avg_duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class ProcessExceptionRow(Base):
    """Agent 1 discovery exceptions. BPM Agent 4 uses app.models.exception.ProcessException."""

    __tablename__ = "exceptions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    process_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    severity: Mapped[str] = mapped_column(Text, nullable=False, default="medium")
    exception_type: Mapped[str] = mapped_column("type", Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    assigned_to: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
