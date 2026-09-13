"""Idempotent, tenant-scoped document ingest for Agent 1."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.agents.agent1_discovery.chunking import chunk_extracted_document
from app.agents.agent1_discovery.document_parser import extract_text_from_bytes
from app.agents.agent1_discovery.schemas import ExtractedDocument
from app.ir.corpus import IndexedDocument, get_document_corpus
from app.ir.hybrid import IndexedChunk
from app.ir.scoring import embed_text

MAX_INDEXED_CHARS = 200_000


def content_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def ingest_bytes(
    *,
    tenant_id: UUID,
    filename: str,
    content: bytes,
    document_id: UUID | None = None,
    process_id: UUID | None = None,
    document_type: str | None = None,
    source: str = "upload",
    version: str = "1",
    mime_type: str | None = None,
    db: Session | None = None,
) -> tuple[IndexedDocument, list[IndexedChunk], ExtractedDocument]:
    """Parse, chunk, and index document bytes. Same tenant+hash is idempotent."""
    digest = content_sha256(content)
    corpus = get_document_corpus()
    existing = corpus.get_by_hash(tenant_id, digest)
    if existing is not None:
        chunks = [
            chunk
            for chunk in corpus.active_chunks(tenant_id)
            if chunk.document_id == existing.document_id
        ]
        extracted = ExtractedDocument(
            file_id=existing.document_id,
            pages=[],
            extraction_confidence=1.0 if existing.parse_status == "extracted" else 0.0,
            extraction_method="idempotent_reuse",
            status="extracted" if existing.parse_status == "extracted" else "failed",
            failure_reason=existing.parse_failure,
        )
        return existing, chunks, extracted

    file_id = document_id or uuid4()
    suffix = Path(filename).suffix.lower()
    extracted = extract_text_from_bytes(file_id, content, suffix=suffix, filename=filename)
    return ingest_extracted(
        tenant_id=tenant_id,
        filename=filename,
        content_hash=digest,
        extracted=extracted,
        process_id=process_id,
        document_type=document_type,
        source=source,
        version=version,
        mime_type=mime_type,
        size_bytes=len(content),
        db=db,
    )


def ingest_extracted(
    *,
    tenant_id: UUID,
    filename: str,
    content_hash: str,
    extracted: ExtractedDocument,
    process_id: UUID | None = None,
    document_type: str | None = None,
    source: str = "upload",
    version: str = "1",
    mime_type: str | None = None,
    size_bytes: int = 0,
    db: Session | None = None,
) -> tuple[IndexedDocument, list[IndexedChunk], ExtractedDocument]:
    corpus = get_document_corpus()
    existing = corpus.get_by_hash(tenant_id, content_hash)
    if existing is not None:
        chunks = [
            chunk
            for chunk in corpus.active_chunks(tenant_id)
            if chunk.document_id == existing.document_id
        ]
        if chunks:
            return existing, chunks, extracted

    parse_ok = extracted.status == "extracted" and any(
        (page.text or "").strip() for page in extracted.pages
    )
    document = IndexedDocument(
        document_id=extracted.file_id,
        tenant_id=tenant_id,
        filename=filename,
        document_type=document_type,
        source=source,
        version=version,
        is_active=True,
        content_hash=content_hash,
        uploaded_at=__now(),
        process_id=process_id,
        mime_type=mime_type,
        size_bytes=size_bytes,
        parse_status="extracted" if parse_ok else "failed",
        parse_failure=None if parse_ok else (extracted.failure_reason or "INSUFFICIENT_EVIDENCE"),
        evidence_ref=str(extracted.file_id),
    )
    chunks: list[IndexedChunk] = []
    if parse_ok:
        bounded = extracted.model_copy(
            update={
                "pages": [
                    page.model_copy(update={"text": (page.text or "")[:MAX_INDEXED_CHARS]})
                    for page in extracted.pages
                ]
            }
        )
        chunks = chunk_extracted_document(
            bounded,
            tenant_id=tenant_id,
            document_id=extracted.file_id,
            document_version=version,
            filename=filename,
            document_type=document_type,
            source=source,
        )
        for chunk in chunks:
            if not chunk.embedding:
                chunk.embedding = embed_text(chunk.text)
    stored = corpus.upsert_document(document, chunks)
    reused = stored.document_id != document.document_id
    if not reused:
        _persist_sql(db, stored, chunks)
        return stored, chunks, extracted
    reused_chunks = [
        chunk for chunk in corpus.active_chunks(tenant_id) if chunk.document_id == stored.document_id
    ]
    return stored, reused_chunks, extracted


def __now():
    from datetime import UTC, datetime

    return datetime.now(UTC)


def _persist_sql(db: Session | None, document: IndexedDocument, chunks: list[IndexedChunk]) -> None:
    if db is None:
        return
    try:
        from app.models.document import DiscoveredDocument, DocumentChunk

        row = db.get(DiscoveredDocument, document.document_id)
        if row is None:
            row = DiscoveredDocument(id=document.document_id)
            db.add(row)
        row.process_id = document.process_id
        row.original_filename = document.filename
        row.sanitized_filename = document.filename
        row.mime_type = document.mime_type
        row.size_bytes = document.size_bytes
        row.ingest_status = document.parse_status
        row.doc_type = document.document_type
        row.tenant_id = document.tenant_id
        row.content_hash = document.content_hash
        row.source = document.source
        row.version = document.version
        row.is_active = document.is_active
        row.evidence_ref = document.evidence_ref
        if not chunks:
            db.commit()
            return
        existing_ids = {
            item.id
            for item in db.query(DocumentChunk.id)
            .filter(
                DocumentChunk.tenant_id == document.tenant_id,
                DocumentChunk.document_id == document.document_id,
            )
            .all()
        }
        for chunk in chunks:
            if chunk.chunk_id in existing_ids:
                continue
            db.add(
                DocumentChunk(
                    id=chunk.chunk_id,
                    tenant_id=chunk.tenant_id,
                    document_id=chunk.document_id,
                    process_id=document.process_id,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page,
                    section_title=chunk.section,
                    text_content=chunk.text[:MAX_INDEXED_CHARS],
                    embedding=list(chunk.embedding),
                    metadata_json=chunk.metadata,
                    document_version=chunk.document_version,
                    is_active=chunk.is_active,
                )
            )
        db.commit()
    except Exception:
        db.rollback()
