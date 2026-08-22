"""API tests for APPROVAL endpoints. No live Supabase database is required."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.agents.agent4_orchestrator.approval_repository import InMemoryApprovalRepository
from app.agents.agent4_orchestrator.approvals import ApprovalService
from app.agents.agent4_orchestrator.constants import ApprovalStatus, RiskLevel, WorkflowStage
from app.agents.agent4_orchestrator.repository import InMemoryProcessRepository
from app.agents.agent4_orchestrator.service import OrchestratorService
from app.api.v1.deps import get_approval_repository, get_approval_service
from app.main import app
from app.tests.auth_helpers import override_current_user


@pytest.fixture
def approval_setup():
    override_current_user(role="approver")
    process_repo = InMemoryProcessRepository()
    approval_repo = InMemoryApprovalRepository()
    orchestrator = OrchestratorService(repository=process_repo)
    approval_service = ApprovalService(
        orchestrator=orchestrator,
        repository=approval_repo,
    )

    async def override_approval_repository() -> InMemoryApprovalRepository:
        return approval_repo

    async def override_approval_service() -> ApprovalService:
        return approval_service

    app.dependency_overrides[get_approval_repository] = override_approval_repository
    app.dependency_overrides[get_approval_service] = override_approval_service

    yield {
        "client": TestClient(app),
        "process_repo": process_repo,
        "approval_repo": approval_repo,
        "orchestrator": orchestrator,
        "approval_service": approval_service,
    }

    app.dependency_overrides.clear()


async def _create_pending_approval(setup, *, reason: str = "Human approval required") -> dict:
    process = await setup["process_repo"].insert_process(
        name="Approval process",
        process_type="procurement",
    )
    await setup["process_repo"].update_process_stage(
        process.id,
        WorkflowStage.AWAITING_HUMAN_APPROVAL,
    )
    record = await setup["approval_repo"].create_approval_request(
        process_id=process.id,
        risk_level=RiskLevel.HIGH,
        reason=reason,
    )
    return {"process": process, "approval": record}


@pytest.mark.asyncio
async def test_list_approvals(approval_setup) -> None:
    setup = approval_setup
    await _create_pending_approval(setup, reason="First")
    await _create_pending_approval(setup, reason="Second")

    response = setup["client"].get("/api/v1/approvals")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    reasons = {item["reason"] for item in body}
    assert reasons == {"First", "Second"}
    for item in body:
        assert item["status"] == ApprovalStatus.PENDING.value


@pytest.mark.asyncio
async def test_list_approvals_filtered_by_pending_status(approval_setup) -> None:
    setup = approval_setup
    first = await _create_pending_approval(setup, reason="Pending one")
    second = await _create_pending_approval(setup, reason="Pending two")
    await setup["approval_service"].approve_request(
        second["approval"].id,
        approver_id=uuid4(),
        comments="Done",
    )

    response = setup["client"].get(
        "/api/v1/approvals",
        params={"status": ApprovalStatus.PENDING.value},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(first["approval"].id)
    assert body[0]["status"] == ApprovalStatus.PENDING.value


@pytest.mark.asyncio
async def test_get_approval(approval_setup) -> None:
    setup = approval_setup
    created = await _create_pending_approval(setup)

    response = setup["client"].get(f"/api/v1/approvals/{created['approval'].id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(created["approval"].id)
    assert body["process_id"] == str(created["process"].id)
    assert body["status"] == ApprovalStatus.PENDING.value
    assert body["decision"] is None


def test_get_unknown_approval_returns_404(approval_setup) -> None:
    response = approval_setup["client"].get(f"/api/v1/approvals/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Approval not found"


@pytest.mark.asyncio
async def test_approve_pending_approval(approval_setup) -> None:
    setup = approval_setup
    created = await _create_pending_approval(setup)

    with patch(
        "app.agents.agent4_orchestrator.communication_service.AgentCommunicationService.send",
        new_callable=AsyncMock,
    ) as send_mock:
        response = setup["client"].post(
            f"/api/v1/approvals/{created['approval'].id}/approve",
            json={"comments": "Approved after review"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == ApprovalStatus.APPROVED.value
    assert body["approval"]["status"] == ApprovalStatus.APPROVED.value
    assert body["approval"]["decision"] == ApprovalStatus.APPROVED.value
    assert body["approval"]["comments"] == "Approved after review"
    assert body["approval"]["decided_at"] is not None
    assert body["approval"]["approver_id"] is not None
    send_mock.assert_not_called()


@pytest.mark.asyncio
async def test_reject_pending_approval(approval_setup) -> None:
    setup = approval_setup
    created = await _create_pending_approval(setup)

    with patch(
        "app.agents.agent4_orchestrator.communication_service.AgentCommunicationService.send",
        new_callable=AsyncMock,
    ) as send_mock:
        response = setup["client"].post(
            f"/api/v1/approvals/{created['approval'].id}/reject",
            json={"comments": "Rejected because evidence is insufficient"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == ApprovalStatus.REJECTED.value
    assert body["approval"]["status"] == ApprovalStatus.REJECTED.value
    assert body["approval"]["decision"] == ApprovalStatus.REJECTED.value
    assert body["approval"]["comments"] == "Rejected because evidence is insufficient"
    assert body["approval"]["decided_at"] is not None
    send_mock.assert_not_called()


@pytest.mark.asyncio
async def test_already_approved_cannot_be_decided_again(approval_setup) -> None:
    setup = approval_setup
    created = await _create_pending_approval(setup)
    approve = setup["client"].post(
        f"/api/v1/approvals/{created['approval'].id}/approve",
        json={"comments": "Approved once"},
    )
    assert approve.status_code == 200

    retry_approve = setup["client"].post(
        f"/api/v1/approvals/{created['approval'].id}/approve",
        json={"comments": "Try again"},
    )
    retry_reject = setup["client"].post(
        f"/api/v1/approvals/{created['approval'].id}/reject",
        json={"comments": "Try reject"},
    )

    assert retry_approve.status_code == 409
    assert retry_reject.status_code == 409
    assert retry_approve.json()["detail"] == "Approval request has already been decided"


@pytest.mark.asyncio
async def test_already_rejected_cannot_be_decided_again(approval_setup) -> None:
    setup = approval_setup
    created = await _create_pending_approval(setup)
    reject = setup["client"].post(
        f"/api/v1/approvals/{created['approval'].id}/reject",
        json={"comments": "Rejected once"},
    )
    assert reject.status_code == 200

    retry_approve = setup["client"].post(
        f"/api/v1/approvals/{created['approval'].id}/approve",
        json={"comments": "Try approve"},
    )
    retry_reject = setup["client"].post(
        f"/api/v1/approvals/{created['approval'].id}/reject",
        json={"comments": "Try again"},
    )

    assert retry_approve.status_code == 409
    assert retry_reject.status_code == 409


@pytest.mark.asyncio
async def test_approve_does_not_execute_agent_2_or_complete_process(approval_setup) -> None:
    setup = approval_setup
    created = await _create_pending_approval(setup)
    process_id = created["process"].id

    with patch(
        "app.agents.agent4_orchestrator.communication_service.AgentCommunicationService.send",
        new_callable=AsyncMock,
    ) as send_mock:
        response = setup["client"].post(
            f"/api/v1/approvals/{created['approval'].id}/approve",
            json={"comments": "Approved after review"},
        )

    assert response.status_code == 200
    send_mock.assert_not_called()
    stage = await setup["orchestrator"].get_current_stage(process_id)
    assert stage is WorkflowStage.AWAITING_HUMAN_APPROVAL
    assert stage is not WorkflowStage.WORKFLOW_EXECUTION
    assert stage is not WorkflowStage.COMPLETED
    process = await setup["process_repo"].get_process(process_id)
    assert process.status == "draft"


@pytest.mark.asyncio
async def test_reject_does_not_execute_agent_2_or_complete_process(approval_setup) -> None:
    setup = approval_setup
    created = await _create_pending_approval(setup)
    process_id = created["process"].id

    with patch(
        "app.agents.agent4_orchestrator.communication_service.AgentCommunicationService.send",
        new_callable=AsyncMock,
    ) as send_mock:
        response = setup["client"].post(
            f"/api/v1/approvals/{created['approval'].id}/reject",
            json={"comments": "Rejected because evidence is insufficient"},
        )

    assert response.status_code == 200
    send_mock.assert_not_called()
    stage = await setup["orchestrator"].get_current_stage(process_id)
    assert stage is WorkflowStage.AWAITING_HUMAN_APPROVAL
    assert stage is not WorkflowStage.COMPLETED
    process = await setup["process_repo"].get_process(process_id)
    assert process.status == "draft"
