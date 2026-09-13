"""In-process tenant-scoped document/chunk index for Agent 1 IR."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from uuid import UUID

from app.ir.hybrid import IndexedChunk, hybrid_search
from app.ir.schemas import RetrievalHit


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class IndexedDocument:
    document_id: UUID
    tenant_id: UUID
    filename: str
    document_type: str | None
    source: str | None
    version: str
    is_active: bool
    content_hash: str
    uploaded_at: datetime
    process_id: UUID | None = None
    mime_type: str | None = None
    size_bytes: int = 0
    parse_status: str = "extracted"
    parse_failure: str | None = None
    evidence_ref: str | None = None
    metadata: dict = field(default_factory=dict)


class DocumentCorpus:
    """Tenant-isolated chunk corpus. Cross-tenant lookup returns nothing."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._documents: dict[tuple[UUID, UUID], IndexedDocument] = {}
        self._by_hash: dict[tuple[UUID, str], UUID] = {}
        self._chunks: dict[UUID, IndexedChunk] = {}

    def reset(self) -> None:
        with self._lock:
            self._documents.clear()
            self._by_hash.clear()
            self._chunks.clear()

    def get_by_hash(self, tenant_id: UUID, content_hash: str) -> IndexedDocument | None:
        with self._lock:
            document_id = self._by_hash.get((tenant_id, content_hash))
            if document_id is None:
                return None
            return self._documents.get((tenant_id, document_id))

    def get_document(self, tenant_id: UUID, document_id: UUID) -> IndexedDocument | None:
        with self._lock:
            return self._documents.get((tenant_id, document_id))

    def get_chunk(self, tenant_id: UUID, chunk_id: UUID) -> IndexedChunk | None:
        with self._lock:
            chunk = self._chunks.get(chunk_id)
            if chunk is None or chunk.tenant_id != tenant_id:
                return None
            return chunk

    def upsert_document(self, document: IndexedDocument, chunks: list[IndexedChunk]) -> IndexedDocument:
        with self._lock:
            existing_id = self._by_hash.get((document.tenant_id, document.content_hash))
            if existing_id is not None:
                existing = self._documents.get((document.tenant_id, existing_id))
                if existing is not None:
                    return existing
            self._documents[(document.tenant_id, document.document_id)] = document
            if document.is_active and document.content_hash:
                self._by_hash[(document.tenant_id, document.content_hash)] = document.document_id
            for chunk in chunks:
                if chunk.tenant_id != document.tenant_id:
                    continue
                self._chunks[chunk.chunk_id] = chunk
            return document

    def search(
        self,
        *,
        tenant_id: UUID,
        query: str,
        top_k: int = 8,
        document_id: UUID | None = None,
    ) -> list[RetrievalHit]:
        with self._lock:
            chunks = [
                chunk
                for chunk in self._chunks.values()
                if chunk.tenant_id == tenant_id
                and chunk.is_active
                and (document_id is None or chunk.document_id == document_id)
            ]
        return hybrid_search(chunks, query, tenant_id=tenant_id, top_k=top_k)

    def active_chunks(self, tenant_id: UUID) -> list[IndexedChunk]:
        with self._lock:
            return [
                chunk
                for chunk in self._chunks.values()
                if chunk.tenant_id == tenant_id and chunk.is_active
            ]


_CORPUS = DocumentCorpus()


def get_document_corpus() -> DocumentCorpus:
    return _CORPUS


def reset_document_corpus() -> None:
    _CORPUS.reset()
