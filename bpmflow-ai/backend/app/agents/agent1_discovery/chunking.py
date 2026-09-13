"""Deterministic page-aware chunking for Agent 1 document intelligence."""

from __future__ import annotations

import re
import uuid
from uuid import UUID

from app.agents.agent1_discovery.schemas import ExtractedDocument, PageText
from app.ir.hybrid import IndexedChunk
from app.ir.scoring import embed_text

MAX_CHUNK_CHARS = 900
_HEADING_RE = re.compile(r"^(\d+(\.\d+)*|[A-Z][A-Z0-9 /&-]{3,80})$")


def _is_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 120:
        return False
    if stripped.endswith("."):
        return False
    if ":" in stripped and any(ch.isdigit() for ch in stripped):
        return False
    if _HEADING_RE.match(stripped):
        return True
    words = stripped.split()
    return 1 <= len(words) <= 12 and stripped[:1].isupper() and not any(ch.isdigit() for ch in stripped)


def _split_page(text: str) -> list[tuple[str | None, str]]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    if not paragraphs:
        lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
        paragraphs = lines or ([text.strip()] if text and text.strip() else [])
    sections: list[tuple[str | None, str]] = []
    heading: str | None = None
    buffer: list[str] = []
    for paragraph in paragraphs:
        first = paragraph.splitlines()[0].strip() if paragraph else ""
        if _is_heading(first) and len(paragraph) < 160:
            if buffer:
                sections.append((heading, "\n".join(buffer)))
                buffer = []
            heading = first
            rest = "\n".join(paragraph.splitlines()[1:]).strip()
            if rest:
                buffer.append(rest)
            continue
        buffer.append(paragraph)
    if buffer:
        sections.append((heading, "\n".join(buffer)))
    return sections


def _window(text: str, max_chars: int) -> list[str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [cleaned]
    pieces: list[str] = []
    start = 0
    overlap = min(80, max_chars // 8)
    while start < len(cleaned):
        end = min(len(cleaned), start + max_chars)
        if end < len(cleaned):
            split_at = cleaned.rfind(" ", start, end)
            if split_at > start + 40:
                end = split_at
        pieces.append(cleaned[start:end].strip())
        if end >= len(cleaned):
            break
        start = max(end - overlap, start + 1)
    return [p for p in pieces if p]


def chunk_extracted_document(
    extracted: ExtractedDocument,
    *,
    tenant_id: UUID,
    document_id: UUID,
    document_version: str = "1",
    filename: str | None = None,
    document_type: str | None = None,
    source: str | None = None,
    max_chars: int = MAX_CHUNK_CHARS,
) -> list[IndexedChunk]:
    """Build deterministic chunks that keep page + heading metadata."""
    pages = extracted.pages or [PageText(page_num=1, text="")]
    chunks: list[IndexedChunk] = []
    index = 0
    for page in pages:
        for section, body in _split_page(page.text or ""):
            for piece in _window(body if not section else f"{section}\n{body}", max_chars):
                digest = uuid.uuid5(
                    document_id,
                    f"{page.page_num}:{index}:{piece[:120]}",
                )
                chunks.append(
                    IndexedChunk(
                        chunk_id=digest,
                        document_id=document_id,
                        tenant_id=tenant_id,
                        page=page.page_num,
                        chunk_index=index,
                        text=piece,
                        embedding=embed_text(piece),
                        document_version=document_version,
                        filename=filename,
                        document_type=document_type,
                        source=source,
                        section=section,
                        is_active=True,
                        metadata={"page": page.page_num, "chunk_index": index},
                    )
                )
                index += 1
    return chunks
