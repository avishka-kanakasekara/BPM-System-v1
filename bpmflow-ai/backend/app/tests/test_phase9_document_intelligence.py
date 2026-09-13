"""Phase 9: Agent 1 document intelligence + hybrid IR."""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agents.agent1_discovery.chunking import chunk_extracted_document
from app.agents.agent1_discovery.document_parser import (
    EXTRACTION_INSUFFICIENT_EVIDENCE,
    extract_text,
    extract_text_from_bytes,
)
from app.agents.agent1_discovery.ingest import content_sha256, ingest_bytes
from app.agents.agent1_discovery.procurement_facts import extract_procurement_facts
from app.agents.agent1_discovery.schemas import ExtractedDocument, PageText
from app.agents.agent1_discovery.service import run_discovery
from app.core.database import Base
from app.ir.corpus import get_document_corpus, reset_document_corpus
from app.ir.hybrid import hybrid_search
from app.ir.scoring import embed_text
from app.process_context.schemas import ProcessContext
from app.process_context.service import merge_process_context

TENANT_A = UUID("00000000-0000-0000-0000-00000000d001")
TENANT_B = UUID("00000000-0000-0000-0000-00000000d099")

HIGH_VALUE_TEXT = """
Purchase Request
PR Number: PR-2026-0098
Requester: Nimal Perera
Department: Information Technology
Item description: Laptop computers for engineering refresh
Quantity: 20
Vendor: TechSource Lanka
Currency: LKR
Total Amount: 1,500,000 LKR
Available budget: 2,000,000 LKR
Number of quotations: 2
Quotation references: Q-11 Q-12
Justification: Replace end-of-life laptops
"""

VIOLATION_TEXT = """
Purchase Request
PR Number: PR-2026-0105
Requester: Kasun Fernando
Department: Operations
Item description: Warehouse scanning hardware
Quantity: 40
Total Amount: 2,500,000 LKR
Available budget: 1,500,000 LKR
Number of quotations: 1
Approver: Kasun Fernando
Justification: Urgent replacement
"""

POLICY_TEXT = """
Procurement Policy Test v1.0
PROC-POL-TEST-1.0

Approval thresholds
Purchases above 1,000,000 LKR require senior management approval.
High-value threshold is 1,000,000 LKR.

Quotation requirements
Purchases above 500,000 LKR require two competitive quotations.

Budget constraints
A purchase must not exceed the available budget.

Segregation of duties
The requester cannot approve the same purchase request.

High-value purchase requirements
High-value purchases require documented quotations and approval authority evidence.

Approval authority
Only designated approvers with sufficient authority may approve.

Evidence requirements
Mandatory quotation, purchase request, and budget evidence must be retained.
"""

BLANK_REQUEST = """
Purchase Request
This document describes a need for office supplies.
No amount is stated.
"""

CONFLICT_TEXT = """
Purchase Request
PR Number: PR-2026-0200
Requester: Amal Silva
Total Amount: 100000 LKR
Total Amount: 250000 LKR
Currency: LKR
"""


class FakeUpload:
    def __init__(self, filename: str, content: bytes, content_type: str | None = None):
        self.filename = filename
        self.content_type = content_type
        self.file = BytesIO(content)


def _pdf_with_text(text: str) -> bytes:
    escaped = (
        text.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", " ")
    )
    lines = [line[:110] for line in escaped.splitlines() if line.strip()] or [" "]
    parts = ["BT /F1 11 Tf 50 760 Td"]
    for index, line in enumerate(lines[:40]):
        if index:
            parts.append("0 -14 Td")
        parts.append(f"({line}) Tj")
    parts.append("ET\n")
    content = "\n".join(parts).encode("latin-1", errors="replace")
    objects = [
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n",
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n",
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n",
        b"<< /Length %d >>stream\n" % len(content) + content + b"endstream\nendobj\n",
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n",
    ]
    header = b"%PDF-1.1\n"
    body = b""
    numbered = []
    cursor = len(header)
    for i, obj in enumerate(objects, start=1):
        if i == 4:
            obj = b"4 0 obj" + obj
        numbered.append(obj)
        body += obj
        cursor += len(obj)
    xref_pos = len(header) + len(body)
    xref = [b"xref\n0 6\n0000000000 65535 f \n"]
    pos = len(header)
    for obj in numbered:
        xref.append(f"{pos:010d} 00000 n \n".encode())
        pos += len(obj)
    trailer = (
        b"".join(xref)
        + f"trailer<</Size 6/Root 1 0 R>>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    )
    return header + body + trailer


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _intelligence(message) -> dict:
    payload = message.payload or {}
    analytics = payload.get("analytics") or {}
    return analytics.get("document_intelligence") or {}


def _fact(message, field: str):
    for item in _intelligence(message).get("facts") or []:
        if item.get("field") == field and not item.get("abstained"):
            return item
    return None


@pytest.fixture(autouse=True)
def _reset_corpus():
    reset_document_corpus()
    yield
    reset_document_corpus()


def test_pdf_ingestion_and_text_extraction_with_page_metadata(tmp_path):
    pdf_path = tmp_path / "Purchase_Request_Test_High_Value.pdf"
    pdf_path.write_bytes(_pdf_with_text(HIGH_VALUE_TEXT))
    extracted = extract_text(uuid4(), pdf_path)
    assert extracted.status == "extracted"
    assert extracted.extraction_method == "pypdf"
    assert extracted.pages[0].page_num == 1
    assert "PR-2026-0098" in extracted.pages[0].text
    assert "1,500,000" in extracted.pages[0].text


def test_extract_text_from_bytes_txt():
    extracted = extract_text_from_bytes(
        uuid4(), HIGH_VALUE_TEXT.encode("utf-8"), suffix="txt", filename="pr.txt"
    )
    assert extracted.status == "extracted"
    assert "Nimal Perera" in extracted.pages[0].text


def test_empty_pdf_is_insufficient_evidence():
    extracted = extract_text_from_bytes(
        uuid4(), b"%PDF-1.1\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n", suffix="pdf"
    )
    assert extracted.status == "failed"
    assert extracted.failure_reason == EXTRACTION_INSUFFICIENT_EVIDENCE


def test_deterministic_chunking_preserves_page_and_index():
    extracted = ExtractedDocument(
        file_id=uuid4(),
        pages=[
            PageText(page_num=1, text="Approval thresholds\nPurchases above 1000000 LKR require approval."),
            PageText(page_num=2, text="Quotation requirements\nTwo competitive quotations are required."),
        ],
        extraction_confidence=1.0,
        extraction_method="text",
        status="extracted",
    )
    chunks = chunk_extracted_document(
        extracted, tenant_id=TENANT_A, document_id=extracted.file_id, filename="policy.pdf"
    )
    assert chunks
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert {chunk.page for chunk in chunks} == {1, 2}
    again = chunk_extracted_document(
        extracted, tenant_id=TENANT_A, document_id=extracted.file_id, filename="policy.pdf"
    )
    assert [c.chunk_id for c in chunks] == [c.chunk_id for c in again]


def test_ingest_idempotent_same_hash():
    content = HIGH_VALUE_TEXT.encode("utf-8")
    first, chunks_a, _ = ingest_bytes(
        tenant_id=TENANT_A, filename="Purchase_Request_Test_High_Value.txt", content=content
    )
    second, chunks_b, _ = ingest_bytes(
        tenant_id=TENANT_A, filename="Purchase_Request_Test_High_Value.txt", content=content
    )
    assert first.document_id == second.document_id
    assert first.content_hash == content_sha256(content)
    assert [c.chunk_id for c in chunks_a] == [c.chunk_id for c in chunks_b]


def test_hybrid_bm25_and_vector_retrieval_with_evidence():
    ingest_bytes(
        tenant_id=TENANT_A,
        filename="Procurement_Policy_Test_v1.0.txt",
        content=POLICY_TEXT.encode("utf-8"),
        document_type="POLICY",
    )
    corpus = get_document_corpus()
    bm25_hits = hybrid_search(
        corpus.active_chunks(TENANT_A),
        "quotation requirements two competitive quotations",
        tenant_id=TENANT_A,
        top_k=5,
    )
    assert bm25_hits
    assert bm25_hits[0].document_id
    assert bm25_hits[0].chunk_id
    assert bm25_hits[0].page is not None
    assert "quotation" in bm25_hits[0].text.lower()
    assert bm25_hits[0].bm25_score > 0 or bm25_hits[0].vector_score > 0
    vector_hits = [
        hit for hit in bm25_hits if hit.vector_score > 0
    ]
    assert vector_hits
    query_vec = embed_text("segregation of duties requester cannot approve")
    assert query_vec
    policy_hits = corpus.search(tenant_id=TENANT_A, query="approval threshold high-value")
    assert any("1,000,000" in hit.text or "1000000" in hit.text.replace(",", "") for hit in policy_hits)


def test_tenant_isolation_and_cross_tenant_rejection():
    ingest_bytes(tenant_id=TENANT_A, filename="a.txt", content=HIGH_VALUE_TEXT.encode())
    ingest_bytes(tenant_id=TENANT_B, filename="b.txt", content=VIOLATION_TEXT.encode())
    hits_a = get_document_corpus().search(tenant_id=TENANT_A, query="PR-2026-0098 laptops")
    hits_b = get_document_corpus().search(tenant_id=TENANT_B, query="PR-2026-0098 laptops")
    assert hits_a
    assert all(hit.tenant_id == TENANT_A for hit in hits_a)
    assert not any("PR-2026-0098" in hit.text for hit in hits_b)
    assert get_document_corpus().get_document(TENANT_B, hits_a[0].document_id) is None
    assert get_document_corpus().get_chunk(TENANT_B, hits_a[0].chunk_id) is None


def test_pr_2026_0098_discovery_facts_and_evidence():
    db = _session()
    message = run_discovery(
        [FakeUpload("Purchase_Request_Test_High_Value.pdf", _pdf_with_text(HIGH_VALUE_TEXT), "application/pdf")],
        db,
        tenant_id=TENANT_A,
    )
    amount = _fact(message, "amount")
    currency = _fact(message, "currency")
    budget = _fact(message, "budget")
    quotes = _fact(message, "quotation_count")
    requester = _fact(message, "requester")
    pr_id = _fact(message, "process_request_id")
    assert amount is not None and Decimal(str(amount["value"])) == Decimal("1500000")
    assert currency["value"] == "LKR"
    assert Decimal(str(budget["value"])) == Decimal("2000000")
    assert int(quotes["value"]) == 2
    assert requester["value"] == "Nimal Perera"
    assert pr_id["value"] == "PR-2026-0098"
    assert amount["evidence_refs"]
    assert amount["evidence_refs"][0]["document_id"]
    assert amount["evidence_refs"][0]["chunk_id"]
    assert amount["confidence"] >= 0.9
    payload = str(message.payload).lower()
    assert "vendor-acme" not in payload


def test_pr_2026_0098_process_context_and_no_workflow_state():
    from app.models.process import Process

    db = _session()
    message = run_discovery(
        [FakeUpload("Purchase_Request_Test_High_Value.pdf", _pdf_with_text(HIGH_VALUE_TEXT), "application/pdf")],
        db,
        tenant_id=TENANT_A,
    )
    row = db.get(Process, message.process_id)
    assert row is not None
    assert row.current_stage == "DRAFT"
    ctx = ProcessContext.model_validate(row.process_context)
    assert ctx.purchase.amount == Decimal("1500000")
    assert ctx.purchase.currency == "LKR"
    assert ctx.budget.available_amount == Decimal("2000000")
    assert ctx.purchase.purchase_request_id == "PR-2026-0098"
    assert ctx.requester.name == "Nimal Perera"
    assert ctx.quotation_count == 2
    assert ctx.evidence
    intel = _intelligence(message)
    assert intel.get("workflow_state") is None
    assert intel.get("completion_state") is None
    assert intel.get("exception_state") is None
    assert intel.get("current_stage") is None
    dumped = str(message.model_dump(mode="json"))
    assert "COMPLETED" not in dumped or "discovery" in dumped.lower()
    assert row.current_stage not in {"COMPLETED", "EXCEPTION"}
    assert "VENDOR-ACME" not in dumped
    assert "IT-OPS" not in dumped


def test_pr_2026_0105_discovers_violation_evidence_without_deciding():
    from app.models.process import Process

    db = _session()
    message = run_discovery(
        [FakeUpload("Purchase_Request_Policy_Violation_Test.pdf", _pdf_with_text(VIOLATION_TEXT), "application/pdf")],
        db,
        tenant_id=TENANT_A,
    )
    assert Decimal(str(_fact(message, "amount")["value"])) == Decimal("2500000")
    assert Decimal(str(_fact(message, "budget")["value"])) == Decimal("1500000")
    assert int(_fact(message, "quotation_count")["value"]) == 1
    assert _fact(message, "requester")["value"] == "Kasun Fernando"
    assert _fact(message, "approver")["value"] == "Kasun Fernando"
    row = db.get(Process, message.process_id)
    assert row.current_stage == "DRAFT"


def test_procurement_policy_discovery_retrieves_citations():
    db = _session()
    message = run_discovery(
        [FakeUpload("Procurement_Policy_Test_v1.0.pdf", _pdf_with_text(POLICY_TEXT), "application/pdf")],
        db,
        tenant_id=TENANT_A,
    )
    hits = _intelligence(message).get("policy_hits") or []
    blob = " ".join(hit.get("text", "") for hit in hits).lower()
    assert hits
    assert "threshold" in blob or "quotation" in blob
    assert all(hit.get("chunk_id") for hit in hits)
    assert all(hit.get("document_id") for hit in hits)


def test_missing_evidence_abstains():
    db = _session()
    message = run_discovery(
        [FakeUpload("blank.pdf", _pdf_with_text(BLANK_REQUEST), "application/pdf")],
        db,
        tenant_id=TENANT_A,
    )
    intel = _intelligence(message)
    assert intel.get("status") == "INSUFFICIENT_EVIDENCE"
    amount = next(f for f in intel["facts"] if f["field"] == "amount")
    assert amount["abstained"] is True
    assert amount["value"] is None
    analytics = (message.payload or {}).get("analytics") or {}
    assert analytics.get("risk_facts", {}).get("purchase_amount") in (None, "")


def test_conflicting_amounts_return_discovery_conflict():
    from app.ir.hybrid import IndexedChunk

    chunk = IndexedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        tenant_id=TENANT_A,
        page=1,
        chunk_index=0,
        text=CONFLICT_TEXT,
        embedding=embed_text(CONFLICT_TEXT),
    )
    direct = extract_procurement_facts([chunk])
    assert direct.status == "DISCOVERY_CONFLICT"
    assert any(item.field == "amount" for item in direct.conflicts)

    db = _session()
    message = run_discovery(
        [FakeUpload("conflict.pdf", _pdf_with_text(CONFLICT_TEXT), "application/pdf")],
        db,
        tenant_id=TENANT_A,
    )
    intel = _intelligence(message)
    assert intel.get("status") == "DISCOVERY_CONFLICT"
    assert any(item["field"] == "amount" for item in intel.get("conflicts") or [])
    amount_fact = next((f for f in intel.get("facts") or [] if f.get("field") == "amount"), None)
    assert amount_fact is None or amount_fact.get("value") is None or amount_fact.get("abstained")


def test_low_confidence_critical_fact_abstains():
    from app.agents.agent1_discovery.procurement_facts import CRITICAL_LOW_CONFIDENCE
    from app.ir.hybrid import IndexedChunk

    weak = IndexedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        tenant_id=TENANT_A,
        page=1,
        chunk_index=0,
        text="maybe some cost around twelve",
        embedding=embed_text("maybe some cost around twelve"),
    )
    extraction = extract_procurement_facts([weak])
    amount = next(f for f in extraction.facts if f.field == "amount")
    assert amount.abstained is True
    assert amount.value is None
    assert extraction.status == "INSUFFICIENT_EVIDENCE"
    assert CRITICAL_LOW_CONFIDENCE > 0


def test_process_context_precedence_not_overwritten_by_weaker_guess():
    process_id = uuid4()
    current = ProcessContext.model_validate(
        {
            "process_id": str(process_id),
            "tenant_id": str(TENANT_A),
            "purchase": {
                "amount": "1500000",
                "currency": "LKR",
                "vendor_name": "TechSource Lanka",
                "amount_source": "extracted_evidence",
            },
        }
    )
    incoming = ProcessContext.model_validate(
        {
            "process_id": str(process_id),
            "tenant_id": str(TENANT_A),
            "purchase": {
                "amount": "5000",
                "currency": "USD",
                "vendor_name": "VENDOR-ACME",
                "amount_source": "agent_derived",
            },
        }
    )
    merged = merge_process_context(current, incoming, incoming_source="agent_derived")
    assert merged.purchase.amount == Decimal("1500000")
    assert merged.purchase.currency == "LKR"
    assert merged.purchase.vendor_name == "TechSource Lanka"


def test_agent1_cannot_mark_completed_or_exception():
    from app.models.process import Process

    db = _session()
    message = run_discovery(
        [FakeUpload("Purchase_Request_Test_High_Value.pdf", _pdf_with_text(HIGH_VALUE_TEXT), "application/pdf")],
        db,
        tenant_id=TENANT_A,
    )
    row = db.get(Process, message.process_id)
    assert row.current_stage == "DRAFT"
    assert row.status != "COMPLETED"
    intel = _intelligence(message)
    assert intel.get("completion_state") is None
    assert intel.get("exception_state") is None
