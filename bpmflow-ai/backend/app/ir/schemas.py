"""Retrieval hit schemas for Agent 1 document intelligence."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EvidencePointer(BaseModel):
    """Traceable pointer from a fact back to a retrieved chunk."""

    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    chunk_id: UUID
    page: int | None = None
    document_version: str | None = None
    source: str | None = None
    section: str | None = None


class RetrievalHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    chunk_id: UUID
    page: int | None = None
    score: float
    text: str
    snippet: str
    document_version: str | None = None
    filename: str | None = None
    document_type: str | None = None
    source: str | None = None
    section: str | None = None
    tenant_id: UUID
    metadata: dict[str, Any] = Field(default_factory=dict)
    bm25_score: float = 0.0
    vector_score: float = 0.0
