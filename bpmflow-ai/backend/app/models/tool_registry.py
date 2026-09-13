"""Persistent tenant-scoped Tool Registry (Phase 5 — definition, not execution)."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base

JsonDict = JSON().with_variant(JSONB(), "postgresql")
JsonList = JSON().with_variant(JSONB(), "postgresql")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ToolRegistryEntry(Base):
    """DB-backed tool registration. Does not store secrets or executable code."""

    __tablename__ = "tool_registry"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="tool_registry_tenant_id_unique"),
        UniqueConstraint(
            "tenant_id", "tool_name", "version",
            name="tool_registry_tenant_name_version_unique",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_category: Mapped[str] = mapped_column(Text, nullable=False)
    action_code: Mapped[str] = mapped_column(Text, nullable=False)
    implementation_key: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False, default="1")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    requires_authorization: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allowed_step_types: Mapped[list] = mapped_column(JsonList, nullable=False, default=list)
    required_permissions: Mapped[list] = mapped_column(JsonList, nullable=False, default=list)
    input_schema: Mapped[dict] = mapped_column(JsonDict, nullable=False, default=dict)
    output_schema: Mapped[dict] = mapped_column(JsonDict, nullable=False, default=dict)
    configuration: Mapped[dict] = mapped_column(JsonDict, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
