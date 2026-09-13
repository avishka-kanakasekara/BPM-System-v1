"""Policy ingestion: store uploaded company documents as versioned knowledge."""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import UUID, uuid4

from .embeddings import embed_text
from .repository import PolicyRepository
from .rule_extractor import chunk_text, extract_rules_from_text
from .schemas import CompanyPolicyRecord, PolicyCreateRequest


class PolicyIngestionService:
    """Ingest policy documents without Agent 4 parsing PDFs itself."""

    def __init__(self, repository: PolicyRepository) -> None:
        self._repository = repository

    async def ingest(
        self,
        *,
        tenant_id: UUID,
        request: PolicyCreateRequest,
        uploaded_by: UUID | None,
        file_bytes: bytes | None = None,
        filename: str | None = None,
    ) -> CompanyPolicyRecord:
        text = (request.text_content or "").strip()
        document_type = request.document_type.lower().lstrip(".")
        document_name = filename or f"{request.name}.{document_type}"
        source_document_id = uuid4()
        storage_path = None

        if file_bytes:
            suffix = Path(filename or f"policy.{document_type}").suffix or f".{document_type}"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(file_bytes)
                storage_path = tmp.name
            extracted = self._extract_file_text(source_document_id, storage_path)
            if extracted:
                text = extracted
            document_type = suffix.lstrip(".").lower() or document_type

        if not text and not request.rules:
            raise ValueError(
                "Policy upload requires text content, an extractable document, or explicit rules"
            )

        chunks = chunk_text(text) if text else []
        for chunk in chunks:
            if chunk.embedding is None:
                chunk.embedding = embed_text(chunk.text_content)
        extracted_rules = extract_rules_from_text(text) if text else []
        # Explicit API rules take precedence; keep extracted rules that don't collide.
        rules = list(request.rules)
        explicit_types = {r.rule_type for r in rules}
        for rule in extracted_rules:
            if rule.rule_type not in explicit_types:
                rules.append(rule)

        return await self._repository.create_policy_version(
            tenant_id=tenant_id,
            request=request,
            chunks=chunks,
            rules=rules,
            uploaded_by=uploaded_by,
            source_document_id=source_document_id,
            storage_path=storage_path,
            document_name=document_name,
            document_type=document_type,
        )

    def _extract_file_text(self, file_id: UUID, path: str) -> str:
        try:
            from app.agents.agent1_discovery.document_parser import extract_text

            extracted = extract_text(file_id, path)
            if extracted.status != "extracted":
                # Fallback for .txt which Agent 1 may not support.
                if path.lower().endswith(".txt"):
                    return Path(path).read_text(encoding="utf-8", errors="replace")
                return ""
            return "\n\n".join(page.text for page in extracted.pages)
        except Exception:
            if path.lower().endswith(".txt"):
                try:
                    return Path(path).read_text(encoding="utf-8", errors="replace")
                except Exception:
                    return ""
            return ""
