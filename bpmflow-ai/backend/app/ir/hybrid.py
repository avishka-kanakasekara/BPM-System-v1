"""Hybrid retrieval: BM25 + vector cosine + optional score fusion.

Uses the existing policy-knowledge scoring primitives. Does not replace IR
with vector-only search.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from uuid import UUID

from app.ir.schemas import RetrievalHit
from app.ir.scoring import bm25_score, cosine_similarity, embed_text, tokenize


class IndexedChunk:
    """Minimal chunk record required by hybrid search."""

    __slots__ = (
        "chunk_id",
        "document_id",
        "tenant_id",
        "page",
        "chunk_index",
        "text",
        "embedding",
        "document_version",
        "filename",
        "document_type",
        "source",
        "section",
        "is_active",
        "metadata",
    )

    def __init__(
        self,
        *,
        chunk_id: UUID,
        document_id: UUID,
        tenant_id: UUID,
        page: int | None,
        chunk_index: int,
        text: str,
        embedding: list[float],
        document_version: str | None = None,
        filename: str | None = None,
        document_type: str | None = None,
        source: str | None = None,
        section: str | None = None,
        is_active: bool = True,
        metadata: dict | None = None,
    ) -> None:
        self.chunk_id = chunk_id
        self.document_id = document_id
        self.tenant_id = tenant_id
        self.page = page
        self.chunk_index = chunk_index
        self.text = text
        self.embedding = embedding
        self.document_version = document_version
        self.filename = filename
        self.document_type = document_type
        self.source = source
        self.section = section
        self.is_active = is_active
        self.metadata = metadata or {}


def hybrid_search(
    chunks: Sequence[IndexedChunk],
    query: str,
    *,
    tenant_id: UUID,
    top_k: int = 8,
    active_only: bool = True,
) -> list[RetrievalHit]:
    """Tenant-filtered hybrid BM25 + vector search over indexed chunks."""
    query_text = (query or "").strip()
    if not query_text:
        return []

    eligible = [
        chunk
        for chunk in chunks
        if chunk.tenant_id == tenant_id and (chunk.is_active or not active_only)
    ]
    if not eligible:
        return []

    query_tokens = tokenize(query_text)
    query_embedding = embed_text(query_text)
    tokenized = [tokenize(chunk.text) for chunk in eligible]
    df: Counter[str] = Counter()
    lengths: list[int] = []
    for tokens in tokenized:
        lengths.append(len(tokens))
        df.update(set(tokens))
    avgdl = sum(lengths) / max(len(lengths), 1)
    n_docs = len(eligible)

    scored: list[tuple[float, float, float, IndexedChunk]] = []
    for chunk, tokens in zip(eligible, tokenized):
        bm25 = bm25_score(query_tokens, tokens, avgdl=avgdl, df=df, n_docs=n_docs)
        vector = 0.0
        if chunk.embedding:
            vector = max(0.0, cosine_similarity(query_embedding, chunk.embedding))
        fused = bm25 + (vector * 2.0 if chunk.embedding else 0.0)
        scored.append((fused, bm25, vector, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    positive = [item for item in scored if item[0] > 0]
    top = (positive or scored)[:top_k]
    max_score = max((item[0] for item in top), default=0.0) or 1.0

    hits: list[RetrievalHit] = []
    for fused, bm25, vector, chunk in top:
        text = chunk.text or ""
        hits.append(
            RetrievalHit(
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
                page=chunk.page,
                score=round(min(1.0, fused / max_score), 6),
                text=text,
                snippet=text[:500],
                document_version=chunk.document_version,
                filename=chunk.filename,
                document_type=chunk.document_type,
                source=chunk.source,
                section=chunk.section,
                tenant_id=chunk.tenant_id,
                metadata=dict(chunk.metadata),
                bm25_score=round(bm25, 6),
                vector_score=round(vector, 6),
            )
        )
    return hits
