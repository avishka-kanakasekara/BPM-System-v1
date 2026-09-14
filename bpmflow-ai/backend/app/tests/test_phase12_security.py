"""Phase 12: authentication, tenant isolation, RBAC, and hardening tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from pydantic import ValidationError

from app.agents.agent4_orchestrator.approval_repository import InMemoryApprovalRepository
from app.agents.agent4_orchestrator.approvals import ApprovalService
from app.agents.agent4_orchestrator.audit_repository import AuditLogRecord, InMemoryAuditRepository
from app.agents.agent4_orchestrator.constants import WorkflowStage
from app.agents.agent4_orchestrator.exception_repository import InMemoryExceptionRepository
from app.agents.agent4_orchestrator.exception_service import ExceptionService
from app.agents.agent4_orchestrator.repository import InMemoryProcessRepository
from app.agents.agent4_orchestrator.service import OrchestratorService
from app.agents.agent4_orchestrator.state_machine import InvalidTransitionError
from app.agents.agent4_orchestrator.workflow import Agent4Workflow
from app.api.v1.deps import get_agent4_workflow, get_audit_repository, get_process_repository
from app.company_directory.seed import BPMFLOW_DEMO_TENANT_ID
from app.core.config import Settings, settings
from app.core.security import NOT_AUTHENTICATED_DETAIL
from app.main import app
from app.procurement.exceptions import CrossTenantProcurementError, PurchaseOrderNotFoundError
from app.procurement.schemas import CreateInvoiceInput, CreatePurchaseOrderInput, LineItemInput
from app.procurement.seed import VENDOR_TECHSOURCE, seed_bpmflow_demo_procurement
from app.procurement.service import get_procurement
from app.tests.auth_helpers import override_current_user
from app.tests.test_phase8c_invoice_matching import _invoice, _po
from app.tool_registry.exceptions import ToolRegistryError
from app.tool_registry.repository import InMemoryToolRegistryRepository
from app.tool_registry.schemas import RegisterToolInput, ToolActionCode, ToolCategory
from app.tool_registry.service import ToolRegistryService

OTHER_TENANT = UUID("00000000-0000-0000-0000-00000000d099")
TEST_SECRET = "test-supabase-jwt-secret-for-unit-tests-only"


def _client_no_auth() -> TestClient:
    app.dependency_overrides.clear()
    return TestClient(app)


def test_unauthenticated_protected_routes_return_401() -> None:
    client = _client_no_auth()
    for path in (
        "/api/v1/processes",
        "/api/v1/audit",
        "/api/v1/exceptions",
        "/api/v1/approvals",
        "/api/v1/vendors",
        "/api/v1/tools",
        f"/api/v1/processes/{uuid4()}/kpis",
        "/api/v1/agent2/dashboard",
    ):
        response = client.get(path)
        assert response.status_code == 401, path
        assert response.json()["detail"] == NOT_AUTHENTICATED_DETAIL
        assert "Traceback" not in response.text
        assert "postgresql://" not in response.text.lower()


def test_malformed_authorization_header_returns_401() -> None:
    client = _client_no_auth()
    response = client.get("/api/v1/processes", headers={"Authorization": "Token abc"})
    assert response.status_code == 401


def test_expired_jwt_cannot_list_processes(monkeypatch) -> None:
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    now = datetime.now(tz=UTC)
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "iat": int(now.timestamp()) - 120,
            "exp": int((now - timedelta(seconds=30)).timestamp()),
            "role": "authenticated",
        },
        TEST_SECRET,
        algorithm="HS256",
    )
    client = _client_no_auth()
    response = client.get("/api/v1/processes", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_requester_cannot_activate_workflow_or_register_tools() -> None:
    override_current_user(role="requester", tenant_id=BPMFLOW_DEMO_TENANT_ID)
    client = TestClient(app)
    activate = client.post(f"/api/v1/workflows/{uuid4()}/activate")
    assert activate.status_code == 403
    register = client.post(
        "/api/v1/tools",
        json={
            "tool_name": "evil",
            "version": "1",
            "tool_category": ToolCategory.PROCUREMENT.value,
            "action_code": ToolActionCode.CREATE_PURCHASE_ORDER.value,
            "implementation_key": "os.system",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
        },
    )
    assert register.status_code == 403
    app.dependency_overrides.clear()


def test_requester_cannot_resolve_exception() -> None:
    override_current_user(role="requester", tenant_id=BPMFLOW_DEMO_TENANT_ID)
    client = TestClient(app)
    response = client.post(
        f"/api/v1/exceptions/{uuid4()}/resolve",
        json={"resolution_notes": "nope"},
    )
    assert response.status_code == 403
    app.dependency_overrides.clear()


def test_approver_cannot_register_tools() -> None:
    override_current_user(role="approver", tenant_id=BPMFLOW_DEMO_TENANT_ID)
    client = TestClient(app)
    response = client.post(
        "/api/v1/tools",
        json={
            "tool_name": "x",
            "version": "1",
            "tool_category": ToolCategory.PROCUREMENT.value,
            "action_code": ToolActionCode.CREATE_PURCHASE_ORDER.value,
            "implementation_key": "procurement.create_purchase_order",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
        },
    )
    assert response.status_code == 403
    app.dependency_overrides.clear()


def test_cross_tenant_process_list_and_get_hidden() -> None:
    override_current_user(role="requester", tenant_id=BPMFLOW_DEMO_TENANT_ID)
    repository = InMemoryProcessRepository()

    async def override_repo() -> InMemoryProcessRepository:
        return repository

    app.dependency_overrides[get_process_repository] = override_repo
    client = TestClient(app)
    mine = client.post("/api/v1/processes", json={"name": "A", "process_type": "procurement"}).json()
    import asyncio

    asyncio.run(
        repository.insert_process(
            name="Secret B",
            process_type="procurement",
            tenant_id=OTHER_TENANT,
        )
    )
    listed = client.get("/api/v1/processes")
    assert listed.status_code == 200
    ids = {row["id"] for row in listed.json()}
    assert mine["id"] in ids
    foreign = [row for row in repository._records.values() if row.tenant_id == OTHER_TENANT][0]
    assert str(foreign.id) not in ids
    hidden = client.get(f"/api/v1/processes/{foreign.id}")
    assert hidden.status_code == 404
    app.dependency_overrides.clear()


def test_cross_tenant_audit_logs_filtered() -> None:
    override_current_user(role="requester", tenant_id=BPMFLOW_DEMO_TENANT_ID)
    repository = InMemoryAuditRepository()
    repository.add_record(
        AuditLogRecord(
            id=uuid4(),
            entity_type="process",
            entity_id=uuid4(),
            action="created",
            timestamp=datetime.now(tz=UTC),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
    )
    repository.add_record(
        AuditLogRecord(
            id=uuid4(),
            entity_type="process",
            entity_id=uuid4(),
            action="secret",
            timestamp=datetime.now(tz=UTC),
            tenant_id=OTHER_TENANT,
        )
    )

    async def override_repo() -> InMemoryAuditRepository:
        return repository

    app.dependency_overrides[get_audit_repository] = override_repo
    client = TestClient(app)
    body = client.get("/api/v1/audit").json()
    assert len(body) == 1
    assert body[0]["action"] == "created"
    app.dependency_overrides.clear()


def test_illegal_draft_invoice_matching_does_not_complete() -> None:
    override_current_user(role="admin", tenant_id=BPMFLOW_DEMO_TENANT_ID)
    repository = InMemoryProcessRepository()
    orchestrator = OrchestratorService(repository=repository)
    workflow = Agent4Workflow(
        orchestrator=orchestrator,
        approval_service=ApprovalService(orchestrator, InMemoryApprovalRepository()),
        exception_service=ExceptionService(orchestrator, InMemoryExceptionRepository()),
    )

    async def override_repo() -> InMemoryProcessRepository:
        return repository

    async def override_wf() -> Agent4Workflow:
        return workflow

    app.dependency_overrides[get_process_repository] = override_repo
    app.dependency_overrides[get_agent4_workflow] = override_wf
    client = TestClient(app)
    created = client.post(
        "/api/v1/processes",
        json={"name": "Still draft", "process_type": "procurement"},
    ).json()
    response = client.post(
        f"/api/v1/processes/{created['id']}/complete-invoice-matching",
        json={"expected_amount": 1.00, "invoice_number": "INV-FORGED"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    fetched = client.get(f"/api/v1/processes/{created['id']}").json()
    assert fetched["current_stage"] == WorkflowStage.DRAFT.value
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_state_machine_rejects_draft_to_completed() -> None:
    repo = InMemoryProcessRepository()
    orchestrator = OrchestratorService(repository=repo)
    process = await repo.insert_process(name="x", process_type="procurement")
    with pytest.raises(InvalidTransitionError):
        await orchestrator.move_process(process.id, WorkflowStage.COMPLETED, reason="bypass")


@pytest.mark.asyncio
async def test_tool_registry_rejects_arbitrary_implementation_key() -> None:
    service = ToolRegistryService(InMemoryToolRegistryRepository())
    with pytest.raises(ToolRegistryError):
        await service.register_tool(
            RegisterToolInput(
                tool_name="pwn",
                version="1",
                tool_category=ToolCategory.PROCUREMENT,
                action_code=ToolActionCode.CREATE_PURCHASE_ORDER,
                implementation_key="os.system",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            ),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )


def test_agent2_full_workflow_path_forbidden() -> None:
    override_current_user(role="requester", tenant_id=BPMFLOW_DEMO_TENANT_ID)
    client = TestClient(app)
    response = client.post(
        "/api/v1/agent2/execute",
        json={
            "process_id": str(uuid4()),
            "task_id": str(uuid4()),
            "tool_name": "__full_task_suite__",
            "parameters": {},
        },
    )
    assert response.status_code in {403, 404}
    app.dependency_overrides.clear()


def test_invoice_matching_ignores_caller_expected_totals() -> None:
    seed_bpmflow_demo_procurement(get_procurement())
    override_current_user(role="approver", tenant_id=BPMFLOW_DEMO_TENANT_ID)
    repository = InMemoryProcessRepository()
    orchestrator = OrchestratorService(repository=repository)
    workflow = Agent4Workflow(
        orchestrator=orchestrator,
        approval_service=ApprovalService(orchestrator, InMemoryApprovalRepository()),
        exception_service=ExceptionService(orchestrator, InMemoryExceptionRepository()),
    )

    async def override_repo() -> InMemoryProcessRepository:
        return repository

    async def override_wf() -> Agent4Workflow:
        return workflow

    app.dependency_overrides[get_process_repository] = override_repo
    app.dependency_overrides[get_agent4_workflow] = override_wf
    client = TestClient(app)
    created = client.post(
        "/api/v1/processes", json={"name": "Match me", "process_type": "procurement"}
    ).json()
    process_id = UUID(created["id"])
    import asyncio

    asyncio.run(repository.update_process_stage(process_id, WorkflowStage.INVOICE_MATCHING))
    po = _po(process_id=process_id)
    _invoice(process_id=process_id, po_id=po.purchase_order_id, number="INV-P12")
    response = client.post(
        f"/api/v1/processes/{process_id}/complete-invoice-matching",
        json={
            "invoice_number": "INV-P12",
            "expected_amount": 0.01,
            "amount": 0.01,
            "expected_currency": "ZZZ",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["current_stage"] == WorkflowStage.COMPLETED.value
    app.dependency_overrides.clear()


def test_cross_tenant_invoice_cannot_point_at_foreign_po() -> None:
    seed_bpmflow_demo_procurement(get_procurement())
    procurement = get_procurement()
    process_id = uuid4()
    po = procurement.create_purchase_order(
        CreatePurchaseOrderInput(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            process_id=process_id,
            vendor_ref=str(VENDOR_TECHSOURCE),
            currency="USD",
            amount=Decimal("10.00"),
            items=[
                LineItemInput(description="Item", quantity=Decimal("1"), unit_price=Decimal("10.00"))
            ],
        )
    )
    with pytest.raises((CrossTenantProcurementError, PurchaseOrderNotFoundError)):
        procurement.create_invoice(
            CreateInvoiceInput(
                tenant_id=OTHER_TENANT,
                process_id=process_id,
                purchase_order_id=po.purchase_order_id,
                vendor_ref=str(VENDOR_TECHSOURCE),
                invoice_number="INV-X",
                currency="USD",
                total=Decimal("10.00"),
                items=[
                    LineItemInput(
                        description="Item", quantity=Decimal("1"), unit_price=Decimal("10.00")
                    )
                ],
            )
        )


def test_negative_invoice_amount_rejected() -> None:
    with pytest.raises(ValidationError):
        CreateInvoiceInput(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            process_id=uuid4(),
            purchase_order_id=uuid4(),
            vendor_ref=str(VENDOR_TECHSOURCE),
            invoice_number="INV-NEG",
            currency="USD",
            total=Decimal("-1.00"),
            items=[],
        )


def test_production_rejects_debug_and_mock_llm() -> None:
    debug = Settings(
        ENV="production",
        DEBUG=True,
        MOCK_LLM=False,
        GEMINI_API_KEY="real-key",
        EMAIL_DRY_RUN=False,
        EMAIL_PROVIDER="resend",
        EMAIL_API_KEY="re_key",
        EMAIL_FROM="noreply@example.com",
        SUPABASE_URL="https://example.supabase.co",
    )
    with pytest.raises(RuntimeError, match="DEBUG"):
        debug.assert_production_config()
    mock = Settings(
        ENV="production",
        DEBUG=False,
        MOCK_LLM=True,
        GEMINI_API_KEY="real-key",
        EMAIL_DRY_RUN=False,
        EMAIL_PROVIDER="resend",
        EMAIL_API_KEY="re_key",
        EMAIL_FROM="noreply@example.com",
        SUPABASE_URL="https://example.supabase.co",
    )
    with pytest.raises(RuntimeError, match="MOCK_LLM"):
        mock.assert_production_config()


def test_phase12_migration_present() -> None:
    path = (
        Path(__file__).resolve().parents[3]
        / "supabase"
        / "migrations"
        / "0024_phase12_rls_hardening.sql"
    )
    text = path.read_text(encoding="utf-8")
    assert "Anyone can view processes" in text
    assert "audit_logs_tenant_authenticated" in text
    assert "approval_requests_tenant_authenticated" in text
    assert "execution_receipts_tenant_authenticated" in text


def test_malformed_json_does_not_leak_internals() -> None:
    override_current_user(role="requester", tenant_id=BPMFLOW_DEMO_TENANT_ID)
    client = TestClient(app)
    response = client.post(
        "/api/v1/processes",
        content="{not-json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "Traceback" not in response.text
    app.dependency_overrides.clear()
