"""Persisted AgentMessage envelope for inter-agent / UI consumption."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base

JsonDict = JSON().with_variant(JSONB(), "postgresql")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentMessageRecord(Base):
    __tablename__ = "agent_messages"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    from_agent: Mapped[str] = mapped_column(Text, nullable=False)
    to_agent: Mapped[str] = mapped_column(Text, nullable=False, default="human")
    message_type: Mapped[str] = mapped_column(Text, nullable=False, default="notification")
    content: Mapped[dict] = mapped_column(JsonDict, nullable=False, default=dict)
    process_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("processes.id"), nullable=True
    )
    task_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="sent")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
