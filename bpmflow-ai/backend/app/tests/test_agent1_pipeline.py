"""Per-stage Agent 1 pipeline tests using real sample documents (G2 prep)."""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.agents.agent1_discovery.document_parser import (
    REASON_MAGIC_BYTE_MISMATCH,
    extract_text,
    validate_and_ingest,
)
from app.agents.agent1_discovery.extractors import (
    classify_document,
    extract_entities,
    extract_relations,
)
from app.agents.agent1_discovery.process_mining import analyze_event_log
from app.agents.agent1_discovery.service import build_process_json, run_discovery
from app.agents.agent1_discovery.step_selection import select_process_steps
from app.agents.agent4_orchestrator.risk_facts import RiskFacts, validate_risk_facts
from app.core.config import settings
from app.core.database import Base
from app.models.audit import IngestionAuditLog
from app.models.process import Process
from app.schemas.agent_message import DiscoveryAgentMessage

SAMPLE_DIR = Path(__file__).resolve().parents[3] / "sample-documents"
PR_DOCX = SAMPLE_DIR / "procurement_purchase_request.docx"
SOP_DOCX = SAMPLE_DIR / "procurement_sop.docx"
EVENT_CSV = SAMPLE_DIR / "procurement_event_log.csv"


class FakeUpload:
    def __init__(self, filename: str, content: bytes, content_type: str | None = None):
        self.filename = filename
        self.content_type = content_type
        self.file = BytesIO(content)


@pytest.fixture
def db_session():
    import app.models  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session: Session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def offline_llm(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_OFFLINE", True)
    monkeypatch.setattr(settings, "MOCK_LLM", False)


def _audit_count(db: Session) -> int:
    return len(list(db.scalars(select(IngestionAuditLog))))


def test_stage_ingest_validates_sample_purchase_request(db_session):
    content = PR_DOCX.read_bytes()
    upload = FakeUpload(
        "procurement_purchase_request.docx",
        content,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    result = validate_and_ingest(upload, db_session)
    assert result.status == "accepted"
    assert _audit_count(db_session) == 1


def test_stage_ingest_rejects_magic_byte_mismatch(db_session):
    upload = FakeUpload("fake.pdf", b"not-a-pdf", "application/pdf")
    result = validate_and_ingest(upload, db_session)
    assert result.status == "rejected"
    assert result.rejection_reason == REASON_MAGIC_BYTE_MISMATCH


def test_stage_extract_text_sample_purchase_request(tmp_path):
    content = PR_DOCX.read_bytes()
    path = tmp_path / "pr.docx"
    path.write_bytes(content)
    extracted = extract_text(uuid4(), path)
    assert extracted.status == "extracted"
    assert "USD 4,565.00" in extracted.pages[0].text
    assert "VENDOR-ACME" in extracted.pages[0].text


def test_stage_classify_sample_purchase_request(tmp_path):
    content = PR_DOCX.read_bytes()
    path = tmp_path / "pr.docx"
    path.write_bytes(content)
    extracted = extract_text(uuid4(), path)
    classification = classify_document(extracted)
    assert classification.doc_type == "PURCHASE_REQUEST"
    assert classification.confidence > 0.5


def test_stage_entities_sample_purchase_request(tmp_path):
    content = PR_DOCX.read_bytes()
    path = tmp_path / "pr.docx"
    path.write_bytes(content)
    extracted = extract_text(uuid4(), path)
    classification = classify_document(extracted)
    entities = extract_entities(extracted, classification.doc_type)
    values = " ".join(entity.value for entity in entities).lower()
    assert "jane smith" in values
    assert "acme" in values
    assert any(entity.entity_type == "amount" for entity in entities)


def test_stage_relations_offline_sample_purchase_request(offline_llm, tmp_path):
    content = PR_DOCX.read_bytes()
    path = tmp_path / "pr.docx"
    path.write_bytes(content)
    extracted = extract_text(uuid4(), path)
    classification = classify_document(extracted)
    entities = extract_entities(extracted, classification.doc_type)
    relations, meta = extract_relations(extracted, entities, classification.doc_type)
    assert meta.degraded is True
    assert meta.method == "rules"
    assert relations
    assert any(relation.predicate == "task-precedes-task" for relation in relations)


def test_stage_mining_sample_event_log():
    result = analyze_event_log(EVENT_CSV)
    assert result.most_frequent_variant == [
        "Submit Purchase Request",
        "Approve Purchase Request",
        "Create Purchase Order",
        "Receive Goods",
        "Pay Invoice",
    ]
    assert result.total_events == 32


def test_stage_step_selection_offline_sample_sop(offline_llm, tmp_path):
    content = SOP_DOCX.read_bytes()
    path = tmp_path / "sop.docx"
    path.write_bytes(content)
    extracted = extract_text(uuid4(), path)
    entities = extract_entities(extracted, "SOP")
    selection, meta = select_process_steps([extracted], entities, [], doc_types=["SOP"])
    assert meta.degraded is True
    assert len(selection.steps) >= 3


def test_stage_build_process_json_with_mining_and_risk_facts(offline_llm, tmp_path):
    content = PR_DOCX.read_bytes()
    pr_path = tmp_path / "pr.docx"
    pr_path.write_bytes(content)
    pr_extracted = extract_text(uuid4(), pr_path)

    mining = analyze_event_log(EVENT_CSV)
    entities = extract_entities(pr_extracted, "PURCHASE_REQUEST")
    relations, _ = extract_relations(pr_extracted, entities, "PURCHASE_REQUEST")
    process = build_process_json(entities, relations, mining)
    joined = pr_extracted.pages[0].text
    risk = RiskFacts.from_discovery(
        entities,
        doc_types=["PURCHASE_REQUEST"],
        joined_text=joined,
        degraded=True,
    )
    process.analytics = {"risk_facts": risk.model_dump(mode="json"), "degraded": True}
    assert len(process.activities) == 5
    assert Decimal(process.analytics["risk_facts"]["purchase_amount"]) == Decimal("4565")
    assert process.analytics["risk_facts"]["vendor_id"] == "VENDOR-ACME"


def test_stage_persist_discovery(db_session, offline_llm):
    message = run_discovery(
        [
            FakeUpload(
                "procurement_purchase_request.docx",
                PR_DOCX.read_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            FakeUpload("procurement_event_log.csv", EVENT_CSV.read_bytes(), "text/csv"),
        ],
        db_session,
    )
    DiscoveryAgentMessage.model_validate(message.model_dump())
    stored = db_session.get(Process, message.process_id)
    assert stored is not None
    assert stored.process_json.get("activities")


def test_g2_offline_sample_documents_produce_valid_model(db_session, offline_llm):
    """G2 gate: sample docs → populated process_json with validated risk_facts."""
    files = [
        FakeUpload(
            "procurement_purchase_request.docx",
            PR_DOCX.read_bytes(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        FakeUpload(
            "procurement_sop.docx",
            SOP_DOCX.read_bytes(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        FakeUpload("procurement_event_log.csv", EVENT_CSV.read_bytes(), "text/csv"),
    ]
    message = run_discovery(files, db_session)
    payload = message.payload

    assert payload.get("activities")
    assert len(payload["activities"]) == 5
    assert payload["analytics"]["degraded"] is True
    assert payload["analytics"]["discovery_stages"]

    risk = validate_risk_facts(payload["analytics"]["risk_facts"])
    assert Decimal(risk.purchase_amount) == Decimal("4565")
    assert risk.currency == "USD"
    assert risk.vendor_id == "VENDOR-ACME"
    assert "purchase_request" in risk.provided_evidence
    assert risk.degraded is True

    assert _audit_count(db_session) == len(files)


def test_g2_mock_llm_sample_documents(db_session, monkeypatch):
    from app.llm import client as llm_client

    monkeypatch.setattr(settings, "MOCK_LLM", True)
    monkeypatch.setattr(settings, "GEMINI_OFFLINE", False)
    monkeypatch.setattr(llm_client.settings, "MOCK_LLM", True)

    files = [
        FakeUpload(
            "procurement_purchase_request.docx",
            PR_DOCX.read_bytes(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        FakeUpload("procurement_event_log.csv", EVENT_CSV.read_bytes(), "text/csv"),
    ]
    message = run_discovery(files, db_session)
    payload = message.payload
    assert len(payload["activities"]) == 5
    risk = validate_risk_facts(payload["analytics"]["risk_facts"])
    assert Decimal(risk.purchase_amount) == Decimal("4565")
    assert payload["analytics"]["degraded"] is False
