"""Uploaded source documents linked to a discovered process."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base

JsonDict = JSON().with_variant(JSONB(), "postgresql")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DiscoveredDocument(Base):
    __tablename__ = "discovered_documents"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    process_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("processes.id", ondelete="CASCADE"), nullable=True
    )
    original_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    sanitized_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ingest_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    doc_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    tenant_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(Text, nullable=False, default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    evidence_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("discovered_documents.id", ondelete="CASCADE"), nullable=False
    )
    process_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list] = mapped_column(JsonDict, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column(JsonDict, nullable=False, default=dict)
    document_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
