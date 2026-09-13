"""Phase 8D: process completion gate and persistent process exceptions."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.agents.agent2_execution.execution.idempotency import clear_memory_receipts
from app.agents.agent4_orchestrator import (
    Agent4Workflow,
    ApprovalService,
    ExceptionService,
    ExceptionStatus,
    InMemoryApprovalRepository,
    InMemoryExceptionRepository,
    OrchestratorService,
    WorkflowStage,
)
from app.agents.agent4_orchestrator.completion_gate import evaluate_procurement_completion
from app.agents.agent4_orchestrator.exceptions import CrossTenantExceptionError
from app.company_directory.seed import BPMFLOW_DEMO_TENANT_ID
from app.procurement.service import get_procurement
from app.tests.test_phase8c_invoice_matching import _invoice, _po


OTHER_TENANT = UUID("00000000-0000-0000-0000-00000000d099")


@pytest.fixture
def workflow_env():
    orchestrator = OrchestratorService()
    exceptions = InMemoryExceptionRepository()
    service = ExceptionService(orchestrator, exceptions)
    workflow = Agent4Workflow(
        orchestrator=orchestrator,
        approval_service=ApprovalService(orchestrator, InMemoryApprovalRepository()),
        exception_service=service,
    )
    return {
        "orchestrator": orchestrator,
        "exceptions": exceptions,
        "service": service,
        "workflow": workflow,
    }


async def _at_invoice_matching(orchestrator) -> UUID:
    process_id = uuid4()
    await orchestrator.create_process(process_id, initial_stage=WorkflowStage.INVOICE_MATCHING)
    return process_id


@pytest.mark.asyncio
class TestPhase8DCompletionAndExceptions:
    async def test_matched_invoice_completes(self, workflow_env):
        process_id = await _at_invoice_matching(workflow_env["orchestrator"])
        po = _po(process_id=process_id)
        _invoice(process_id=process_id, po_id=po.purchase_order_id, number="INV-8D-OK")
        result = await workflow_env["workflow"].complete_invoice_matching(
            process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID, invoice_number="INV-8D-OK"
        )
        assert result.success is True
        assert result.current_stage is WorkflowStage.COMPLETED
        assert await workflow_env["service"].list_blocking_exceptions(process_id) == []

    async def test_missing_invoice_cannot_complete(self, workflow_env):
        process_id = await _at_invoice_matching(workflow_env["orchestrator"])
        _po(process_id=process_id)
        result = await workflow_env["workflow"].complete_invoice_matching(
            process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        assert result.success is False
        assert result.error_code == "INVOICE_INSUFFICIENT_EVIDENCE"
        assert await workflow_env["orchestrator"].get_current_stage(process_id) is WorkflowStage.INVOICE_MATCHING

    async def test_missing_po_cannot_complete(self, workflow_env):
        process_id = await _at_invoice_matching(workflow_env["orchestrator"])
        result = await workflow_env["workflow"].complete_invoice_matching(
            process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        assert result.success is False
        assert result.error_code == "INVOICE_INSUFFICIENT_EVIDENCE"
        assert await workflow_env["orchestrator"].get_current_stage(process_id) is WorkflowStage.INVOICE_MATCHING

    async def test_unmatched_invoice_cannot_complete(self, workflow_env):
        process_id = await _at_invoice_matching(workflow_env["orchestrator"])
        po = _po(process_id=process_id)
        invoice = _invoice(process_id=process_id, po_id=po.purchase_order_id, number="INV-8D-OPEN")
        stored = get_procurement().get_invoice(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, invoice_id=invoice.invoice_id
        )
        assert stored is not None
        assert stored.status != "MATCHED"
        gate = evaluate_procurement_completion(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            process_id=process_id,
            current_stage=WorkflowStage.INVOICE_MATCHING,
            exceptions=[],
        )
        assert gate.allowed is False
        assert gate.error_code == "INVOICE_NOT_MATCHED"

    async def test_mismatch_creates_persistent_exception(self, workflow_env):
        process_id = await _at_invoice_matching(workflow_env["orchestrator"])
        po = _po(process_id=process_id)
        _invoice(
            process_id=process_id,
            po_id=po.purchase_order_id,
            number="INV-8D-AMT",
            total="1600000",
            subtotal="1600000",
            qty="20",
            unit="80000",
        )
        result = await workflow_env["workflow"].complete_invoice_matching(
            process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID, invoice_number="INV-8D-AMT"
        )
        assert result.success is False
        assert result.error_code == "AMOUNT_MISMATCH"
        assert result.current_stage is WorkflowStage.EXCEPTION
        assert result.bpm_exception is not None
        assert result.bpm_exception.status is ExceptionStatus.OPEN
        assert result.bpm_exception.exception_code == "AMOUNT_MISMATCH"
        invoice = get_procurement().list_invoices(
            tenant_id=BPMFLOW_DEMO_TENANT_ID, process_id=process_id
        )[0]
        assert invoice.status == "MISMATCH"
        assert invoice.match_result
        rows = await workflow_env["service"].list_exceptions(process_id=process_id)
        assert len(rows) == 1

    async def test_repeated_mismatch_does_not_duplicate_exception(self, workflow_env):
        process_id = await _at_invoice_matching(workflow_env["orchestrator"])
        po = _po(process_id=process_id)
        _invoice(
            process_id=process_id,
            po_id=po.purchase_order_id,
            number="INV-8D-DUP",
            total="1600000",
            subtotal="1600000",
            qty="20",
            unit="80000",
        )
        first = await workflow_env["workflow"].complete_invoice_matching(
            process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID, invoice_number="INV-8D-DUP"
        )
        second = await workflow_env["workflow"].complete_invoice_matching(
            process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID, invoice_number="INV-8D-DUP"
        )
        assert first.bpm_exception is not None
        assert second.error_code == "INVALID_STAGE"
        rows = await workflow_env["service"].list_exceptions(process_id=process_id)
        assert len(rows) == 1
        again = await workflow_env["service"].create_exception(
            process_id,
            first.bpm_exception.description,
            exception_code="AMOUNT_MISMATCH",
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            details={"invoice_id": str(first.bpm_exception.details.get("invoice_id"))},
        )
        assert again.id == first.bpm_exception.id

    async def test_exception_resolution_does_not_complete(self, workflow_env):
        process_id = await _at_invoice_matching(workflow_env["orchestrator"])
        po = _po(process_id=process_id)
        _invoice(
            process_id=process_id,
            po_id=po.purchase_order_id,
            number="INV-8D-RES",
            total="1600000",
            subtotal="1600000",
            qty="20",
            unit="80000",
        )
        mismatch = await workflow_env["workflow"].complete_invoice_matching(
            process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID, invoice_number="INV-8D-RES"
        )
        resolved = await workflow_env["service"].resolve_exception(
            mismatch.bpm_exception.id,
            resolution_notes="Human reviewed mismatch",
            performed_by=uuid4(),
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        assert resolved.status is ExceptionStatus.RESOLVED
        assert await workflow_env["orchestrator"].get_current_stage(process_id) is WorkflowStage.EXCEPTION
        gate = evaluate_procurement_completion(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            process_id=process_id,
            current_stage=WorkflowStage.EXCEPTION,
            exceptions=await workflow_env["service"].list_blocking_exceptions(process_id),
        )
        assert gate.allowed is False

    async def test_unresolved_exception_blocks_completion(self, workflow_env):
        process_id = await _at_invoice_matching(workflow_env["orchestrator"])
        po = _po(process_id=process_id)
        _invoice(process_id=process_id, po_id=po.purchase_order_id, number="INV-8D-BLOCK")
        await workflow_env["service"].create_exception(
            process_id,
            "Open blocker",
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            halt_process=False,
        )
        result = await workflow_env["workflow"].complete_invoice_matching(
            process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID, invoice_number="INV-8D-BLOCK"
        )
        assert result.success is False
        assert result.error_code == "OPEN_EXCEPTION"
        assert await workflow_env["orchestrator"].get_current_stage(process_id) is WorkflowStage.INVOICE_MATCHING

    async def test_cross_tenant_exception_access_denied(self, workflow_env):
        process_id = await _at_invoice_matching(workflow_env["orchestrator"])
        record = await workflow_env["service"].create_exception(
            process_id,
            "Tenant A issue",
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            halt_process=False,
        )
        with pytest.raises(CrossTenantExceptionError):
            await workflow_env["service"].get_exception(record.id, tenant_id=OTHER_TENANT)
        with pytest.raises(CrossTenantExceptionError):
            await workflow_env["service"].resolve_exception(
                record.id, "nope", tenant_id=OTHER_TENANT
            )
        loaded = await workflow_env["service"].get_exception(
            record.id, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        assert loaded.status is ExceptionStatus.OPEN

    async def test_agent2_cannot_mark_process_completed_or_exception(self):
        clear_memory_receipts()
        from app.agents.agent2_execution.workflow_step.executor import WorkflowStepExecutor
        from app.agents.agent4_orchestrator.repository import InMemoryProcessRepository

        processes = InMemoryProcessRepository()
        record = await processes.insert_process(
            name="Agent2 cannot complete",
            process_type="procurement",
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        await processes.update_process_stage(record.id, WorkflowStage.WORKFLOW_EXECUTION)
        assert hasattr(WorkflowStepExecutor, "execute_one_step")
        assert not hasattr(WorkflowStepExecutor, "move_process")
        stage = await processes.get_process_stage(record.id)
        assert stage is WorkflowStage.WORKFLOW_EXECUTION
        assert stage is not WorkflowStage.COMPLETED
        assert stage is not WorkflowStage.EXCEPTION

    async def test_agent4_converts_step_failure_to_exception(self, workflow_env):
        process_id = uuid4()
        await workflow_env["orchestrator"].create_process(
            process_id, initial_stage=WorkflowStage.WORKFLOW_EXECUTION
        )
        result = await workflow_env["workflow"].capture_failure(
            process_id,
            "Required tool failed",
            exception_code="TOOL_FAILURE",
            source_agent="agent2",
            source_operation="execute_authorized",
            details={"execution_event_id": str(process_id)},
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        assert result.current_stage is WorkflowStage.EXCEPTION
        assert result.bpm_exception is not None
        assert result.bpm_exception.exception_code == "TOOL_FAILURE"
        again = await workflow_env["workflow"].capture_failure(
            process_id,
            "Required tool failed",
            exception_code="TOOL_FAILURE",
            details={"execution_event_id": str(process_id)},
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
        )
        assert again.bpm_exception.id == result.bpm_exception.id
        audits = [
            event
            for event in workflow_env["exceptions"].audit_events
            if event.get("action") == "created"
        ]
        assert len(audits) == 1

    async def test_pr_2026_0098_can_complete(self, workflow_env):
        process_id = await _at_invoice_matching(workflow_env["orchestrator"])
        po = _po(process_id=process_id)
        _invoice(process_id=process_id, po_id=po.purchase_order_id, number="INV-PR-2026-0098")
        result = await workflow_env["workflow"].complete_invoice_matching(
            process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID, invoice_number="INV-PR-2026-0098"
        )
        assert result.success is True
        assert result.current_stage is WorkflowStage.COMPLETED

    async def test_pr_2026_0105_remains_blocked(self, workflow_env):
        process_id = uuid4()
        await workflow_env["orchestrator"].create_process(
            process_id, initial_stage=WorkflowStage.RESOURCE_PLANNING
        )
        result = await workflow_env["workflow"].complete_invoice_matching(
            process_id, tenant_id=BPMFLOW_DEMO_TENANT_ID
        )
        assert result.success is False
        assert result.error_code == "INVALID_STAGE"
        assert await workflow_env["orchestrator"].get_current_stage(process_id) is WorkflowStage.RESOURCE_PLANNING
        await workflow_env["service"].create_exception(
            process_id,
            "PR-2026-0105 budget exceeded, missing quotation, SoD violation",
            exception_code="BUDGET_EXCEEDED",
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            halt_process=False,
            details={"purchase_request_id": "PR-2026-0105"},
        )
        gate = evaluate_procurement_completion(
            tenant_id=BPMFLOW_DEMO_TENANT_ID,
            process_id=process_id,
            current_stage=WorkflowStage.RESOURCE_PLANNING,
            exceptions=await workflow_env["service"].list_blocking_exceptions(process_id),
        )
        assert gate.allowed is False
        assert await workflow_env["orchestrator"].get_current_stage(process_id) is not WorkflowStage.COMPLETED
