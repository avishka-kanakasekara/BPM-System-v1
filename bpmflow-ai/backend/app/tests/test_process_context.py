"""Phase 1: canonical ProcessContext — no invented business facts."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.agents.agent1_discovery.schemas import Entity, ProcessJSON
from app.agents.agent4_orchestrator.execution_payload import (
    ExecutionEnrichmentError,
    require_enrich_execute_parameters,
)
from app.agents.agent4_orchestrator.risk_facts import RiskFacts
from app.process_context.exceptions import MissingRequiredContextError
from app.process_context.from_discovery import context_from_discovery
from app.process_context.identity import (
    IdentityLink,
    clear_identity_links,
    register_identity_link,
    resolve_employee_resource_id,
)
from app.process_context.schemas import PurchaseFacts
from app.process_context.service import (
    context_from_process_row,
    empty_process_context,
    merge_process_context,
)
from app.schemas.agent_message import DiscoveryAgentMessage


def _entity(entity_type: str, value: str) -> Entity:
    return Entity(
        entity_type=entity_type,
        value=value,
        source_page=1,
        char_span=(0, len(value)),
        confidence=0.9,
    )


def _message(process_id, payload: dict | None = None) -> DiscoveryAgentMessage:
    return DiscoveryAgentMessage(
        process_id=process_id,
        payload=payload or {},
        status="COMPLETE",
        overall_confidence=0.9,
        evidence_references=[],
    )


class TestAmountCurrencySurvive:
    def test_lkr_amount_survives_discovery_to_agent4_context(self) -> None:
        process_id = uuid4()
        process = ProcessJSON(
            process_name="Laptop purchase",
            analytics={
                "risk_facts": RiskFacts(
                    purchase_amount="2500000",
                    currency="LKR",
                    vendor_id="V-EXTRACTED",
                    extraction_method="rules",
                ).model_dump(mode="json")
            },
        )
        ctx = context_from_discovery(process, _message(process_id, process.model_dump(mode="json")))
        assert ctx.purchase.amount == Decimal("2500000")
        assert ctx.purchase.currency == "LKR"
        # Agent 4 enrichment must keep the same facts.
        enriched = require_enrich_execute_parameters(
            process_id=str(process_id),
            process_type="PROCUREMENT",
            process_name="Laptop purchase",
            metadata_json={
                "process_context": ctx.model_dump(mode="json"),
                "process_json": process.model_dump(mode="json"),
            },
            parameters={},
        )
        assert enriched["amount"] == 2500000.0
        assert enriched["currency"] == "LKR"
        assert enriched["vendor_id"] == "V-EXTRACTED"


class TestBudgetSurvives:
    def test_budget_1500000_remains_intact(self) -> None:
        process_id = uuid4()
        process = ProcessJSON(
            analytics={
                "risk_facts": {
                    "purchase_amount": "2500000",
                    "currency": "LKR",
                    "budget_amount": "1500000",
                    "budget_currency": "LKR",
                }
            }
        )
        ctx = context_from_discovery(process, _message(process_id))
        assert ctx.budget.available_amount == Decimal("1500000")
        assert ctx.budget.currency == "LKR"
        later = merge_process_context(
            ctx,
            empty_process_context(process_id).model_copy(
                update={"purchase": PurchaseFacts(amount=Decimal("2500000"), currency="LKR")}
            ),
            incoming_source="agent_derived",
        )
        assert later.budget.available_amount == Decimal("1500000")


class TestQuotations:
    def test_quotation_count_one_remains_one(self) -> None:
        process_id = uuid4()
        file_id = uuid4()
        process = ProcessJSON(analytics={"risk_facts": {"currency": "LKR"}})
        ctx = context_from_discovery(
            process,
            _message(process_id),
            documents=[{"file_id": file_id, "doc_type": "QUOTATION"}],
            doc_types=["QUOTATION"],
        )
        assert ctx.quotation_count == 1

    def test_multiple_quotations_remain_individually_represented(self) -> None:
        process_id = uuid4()
        docs = [
            {"file_id": uuid4(), "doc_type": "QUOTATION"},
            {"file_id": uuid4(), "doc_type": "QUOTATION"},
        ]
        ctx = context_from_discovery(
            ProcessJSON(),
            _message(process_id),
            documents=docs,
            doc_types=["QUOTATION", "QUOTATION"],
        )
        assert ctx.quotation_count == 2
        assert ctx.quotations[0].quotation_id != ctx.quotations[1].quotation_id


class TestNoInventedDefaults:
    def test_missing_amount_does_not_become_5000_usd(self) -> None:
        with pytest.raises(ExecutionEnrichmentError) as exc:
            require_enrich_execute_parameters(
                process_id=str(uuid4()),
                process_type="PROCUREMENT",
                process_name="Test",
                metadata_json={},
                parameters={},
            )
        assert exc.value.missing_fields
        assert "5000" not in str(exc.value)
        ctx = empty_process_context(uuid4())
        assert ctx.purchase.amount is None
        assert ctx.purchase.currency is None

    def test_missing_vendor_does_not_become_vendor_acme(self) -> None:
        process_id = uuid4()
        ctx = empty_process_context(process_id).model_copy(
            update={"purchase": PurchaseFacts(amount=Decimal("2500000"), currency="LKR")}
        )
        with pytest.raises(ExecutionEnrichmentError) as exc:
            require_enrich_execute_parameters(
                process_id=str(process_id),
                process_type="PROCUREMENT",
                process_name="Test",
                metadata_json={"process_context": ctx.model_dump(mode="json")},
                parameters={},
            )
        assert "purchase.vendor_id" in exc.value.missing_fields
        assert "VENDOR-ACME" not in str(exc.value)


class TestIdentityDistinct:
    def test_unmapped_user_id_is_not_employee_resource_id(self) -> None:
        clear_identity_links()
        user_id = uuid4()
        tenant_id = uuid4()
        process = ProcessJSON()
        ctx = context_from_discovery(
            process,
            _message(uuid4()),
            tenant_id=tenant_id,
            requester_user_id=user_id,
        )
        assert ctx.requester.user_id == user_id
        assert ctx.requester.employee_resource_id is None
        assert ctx.requester.identity_mapped is False
        assert resolve_employee_resource_id(user_id=user_id, tenant_id=tenant_id) is None

    def test_mapped_identity_stays_two_ids(self) -> None:
        clear_identity_links()
        user_id = uuid4()
        tenant_id = uuid4()
        resource_id = uuid4()
        register_identity_link(
            IdentityLink(tenant_id=tenant_id, user_id=user_id, employee_resource_id=resource_id)
        )
        ctx = context_from_discovery(
            ProcessJSON(),
            _message(uuid4()),
            tenant_id=tenant_id,
            requester_user_id=user_id,
        )
        assert ctx.requester.user_id == user_id
        assert ctx.requester.employee_resource_id == resource_id
        assert ctx.requester.user_id != ctx.requester.employee_resource_id
        clear_identity_links()


class TestTenantIsolation:
    def test_cannot_merge_across_tenants(self) -> None:
        process_id = uuid4()
        left = empty_process_context(process_id, tenant_id=uuid4())
        right = empty_process_context(process_id, tenant_id=uuid4())
        with pytest.raises(ValueError, match="across tenants"):
            merge_process_context(left, right, incoming_source="extracted_evidence")

    def test_context_from_row_keeps_tenant(self) -> None:
        tenant = uuid4()
        process_id = uuid4()
        row = type(
            "Row",
            (),
            {
                "id": process_id,
                "tenant_id": tenant,
                "process_context": empty_process_context(process_id, tenant_id=tenant).model_dump(
                    mode="json"
                ),
                "created_by": None,
                "requester_email": None,
                "department": None,
            },
        )()
        loaded = context_from_process_row(row)
        assert loaded.tenant_id == tenant
        assert loaded.process_id == process_id


class TestMissingRequiredContext:
    def test_structured_error_code(self) -> None:
        err = MissingRequiredContextError("purchase.amount")
        assert err.error_code == "MISSING_REQUIRED_CONTEXT"
        assert err.as_dict()["field"] == "purchase.amount"
