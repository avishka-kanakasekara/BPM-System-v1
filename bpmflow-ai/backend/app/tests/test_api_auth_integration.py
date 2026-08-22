"""Section 12B: authenticated Agent 4 API integration tests."""

from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.agents.agent4_orchestrator.approval_repository import InMemoryApprovalRepository
from app.agents.agent4_orchestrator.approvals import ApprovalService
from app.agents.agent4_orchestrator.audit_repository import InMemoryAuditRepository
from app.agents.agent4_orchestrator.constants import (
    ApprovalStatus,
    ExceptionSeverity,
    ExceptionType,
    RiskLevel,
    WorkflowStage,
)
from app.agents.agent4_orchestrator.exception_repository import InMemoryExceptionRepository
from app.agents.agent4_orchestrator.exception_service import ExceptionService
from app.agents.agent4_orchestrator.repository import InMemoryProcessRepository
from app.agents.agent4_orchestrator.service import OrchestratorService
from app.agents.agent4_orchestrator.workflow import Agent4Workflow
from app.api.v1.deps import (
    get_agent4_workflow,
    get_approval_repository,
    get_approval_service,
    get_audit_repository,
    get_exception_repository,
    get_exception_service,
    get_process_repository,
)
from app.core.security import NOT_AUTHENTICATED_DETAIL, get_current_user
from app.main import app
from app.tests.auth_helpers import override_current_user

FORBIDDEN_DETAIL = "Insufficient permissions"
ALREADY_DECIDED_DETAIL = "Approval request has already been decided"


def _agent2_success_reply(message):
    """Well-formed Agent 2 execution response for the approve continuation."""
    from app.schemas.agent_message import (
        AGENT_2,
        AGENT_4,
        AgentMessage,
        AgentMessageMetadata,
        AgentMessageType,
    )

    return AgentMessage(
        metadata=AgentMessageMetadata(
            correlation_id=message.metadata.correlation_id,
            process_instance_id=message.metadata.process_instance_id,
            task_id=message.metadata.task_id,
            sender=AGENT_2,
            receiver=AGENT_4,
            message_type=AgentMessageType.WORKFLOW_EXECUTION_RESPONSE,
        ),
        payload={"receipt_status": "SUCCESS"},
        status="EXECUTION_RESULT",
    )


def _patch_agent2_send():
    return patch(
        "app.agents.agent4_orchestrator.communication_service.AgentCommunicationService.send",
        new_callable=AsyncMock,
        side_effect=_agent2_success_reply,
    )


@pytest.fixture
def api_setup():
    process_repo = InMemoryProcessRepository()
    approval_repo = InMemoryApprovalRepository()
    exception_repo = InMemoryExceptionRepository()
    audit_repo = InMemoryAuditRepository()
    orchestrator = OrchestratorService(repository=process_repo)
    approval_service = ApprovalService(
        orchestrator=orchestrator,
        repository=approval_repo,
    )
    exception_service = ExceptionService(
        orchestrator=orchestrator,
        repository=exception_repo,
    )
    workflow = Agent4Workflow(
        orchestrator=orchestrator,
        approval_service=approval_service,
        exception_service=exception_service,
    )

    async def override_process_repo():
        return process_repo

    async def override_approval_repo():
        return approval_repo

    async def override_exception_repo():
        return exception_repo

    async def override_audit_repo():
        return audit_repo

    async def override_approval_svc():
        return approval_service

    async def override_exception_svc():
        return exception_service

    async def override_workflow():
        return workflow

    app.dependency_overrides[get_process_repository] = override_process_repo
    app.dependency_overrides[get_approval_repository] = override_approval_repo
    app.dependency_overrides[get_exception_repository] = override_exception_repo
    app.dependency_overrides[get_audit_repository] = override_audit_repo
    app.dependency_overrides[get_approval_service] = override_approval_svc
    app.dependency_overrides[get_exception_service] = override_exception_svc
    app.dependency_overrides[get_agent4_workflow] = override_workflow

    yield {
        "client": TestClient(app),
        "process_repo": process_repo,
        "approval_repo": approval_repo,
        "exception_repo": exception_repo,
        "audit_repo": audit_repo,
        "orchestrator": orchestrator,
        "approval_service": approval_service,
        "exception_service": exception_service,
    }

    app.dependency_overrides.clear()


def _clear_auth() -> None:
    app.dependency_overrides.pop(get_current_user, None)


def _assert_401(response) -> None:
    assert response.status_code == 401
    assert response.json()["detail"] == NOT_AUTHENTICATED_DETAIL


def _assert_403(response) -> None:
    assert response.status_code == 403
    assert response.json()["detail"] == FORBIDDEN_DETAIL


def _create_process(client: TestClient, **extra_fields) -> dict:
    payload = {
        "name": "Auth test process",
        "process_type": "procurement",
        "description": "Section 12B",
    }
    payload.update(extra_fields)
    response = client.post("/api/v1/processes", json=payload)
    assert response.status_code == 201
    return response.json()


async def _create_pending_approval(setup) -> dict:
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
        reason="Human approval required",
    )
    return {"process": process, "approval": record}


async def _create_open_exception(setup) -> dict:
    process = await setup["process_repo"].insert_process(
        name="Exception process",
        process_type="procurement",
    )
    await setup["process_repo"].update_process_stage(
        process.id,
        WorkflowStage.WORKFLOW_EXECUTION,
    )
    record = await setup["exception_service"].create_exception(
        process.id,
        description="System issue",
        severity=ExceptionSeverity.HIGH,
        exception_type=ExceptionType.SYSTEM_ERROR,
    )
    return {"process": process, "exception": record}


# --- PROCESS ---


def test_unauthenticated_create_process_returns_401(api_setup) -> None:
    _clear_auth()
    response = api_setup["client"].post(
        "/api/v1/processes",
        json={"name": "P", "process_type": "procurement"},
    )
    _assert_401(response)


def test_authenticated_requester_create_process_success(api_setup) -> None:
    override_current_user(role="requester")
    body = _create_process(api_setup["client"])
    assert body["status"] == "draft"
    assert body["current_stage"] == WorkflowStage.DRAFT.value


def test_create_process_sets_created_by_from_current_user(api_setup) -> None:
    user_id = override_current_user(role="requester")
    body = _create_process(api_setup["client"])
    assert body["created_by"] == str(user_id)


def test_client_cannot_override_created_by(api_setup) -> None:
    user_id = override_current_user(role="requester")
    spoofed = uuid4()
    body = _create_process(
        api_setup["client"],
        created_by=str(spoofed),
        id=str(uuid4()),
    )
    assert body["created_by"] == str(user_id)
    assert body["created_by"] != str(spoofed)


def test_unauthenticated_start_process_returns_401(api_setup) -> None:
    _clear_auth()
    response = api_setup["client"].post(f"/api/v1/processes/{uuid4()}/start")
    _assert_401(response)


def test_authenticated_start_process_executes_workflow(api_setup) -> None:
    override_current_user(role="requester")
    created = _create_process(api_setup["client"])
    response = api_setup["client"].post(f"/api/v1/processes/{created['id']}/start")
    assert response.status_code == 200
    body = response.json()
    assert body["process"]["current_stage"] == WorkflowStage.DISCOVERING.value


def test_start_process_stage_correct_when_agent_1_unavailable(api_setup) -> None:
    override_current_user(role="requester")
    created = _create_process(api_setup["client"])
    response = api_setup["client"].post(f"/api/v1/processes/{created['id']}/start")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error_code"] == "AGENT_UNAVAILABLE"
    assert body["process"]["current_stage"] == WorkflowStage.DISCOVERING.value


# --- APPROVAL ---


def test_unauthenticated_approve_returns_401(api_setup) -> None:
    _clear_auth()
    response = api_setup["client"].post(
        f"/api/v1/approvals/{uuid4()}/approve",
        json={"comments": "nope"},
    )
    _assert_401(response)


@pytest.mark.asyncio
async def test_requester_approve_returns_403(api_setup) -> None:
    setup = api_setup
    override_current_user(role="requester")
    created = await _create_pending_approval(setup)
    response = setup["client"].post(
        f"/api/v1/approvals/{created['approval'].id}/approve",
        json={"comments": "Should fail"},
    )
    _assert_403(response)


@pytest.mark.asyncio
async def test_approver_approve_success(api_setup) -> None:
    setup = api_setup
    approver_id = override_current_user(role="approver")
    created = await _create_pending_approval(setup)
    with _patch_agent2_send():
        response = setup["client"].post(
            f"/api/v1/approvals/{created['approval'].id}/approve",
            json={"comments": "Approved"},
        )
    assert response.status_code == 200
    assert response.json()["decision"] == ApprovalStatus.APPROVED.value
    assert response.json()["approval"]["approver_id"] == str(approver_id)


@pytest.mark.asyncio
async def test_admin_approve_success(api_setup) -> None:
    setup = api_setup
    admin_id = override_current_user(role="admin")
    created = await _create_pending_approval(setup)
    with _patch_agent2_send():
        response = setup["client"].post(
            f"/api/v1/approvals/{created['approval'].id}/approve",
            json={"comments": "Admin approved"},
        )
    assert response.status_code == 200
    assert response.json()["approval"]["approver_id"] == str(admin_id)


@pytest.mark.asyncio
async def test_approver_id_equals_current_user_on_approve(api_setup) -> None:
    setup = api_setup
    approver_id = override_current_user(role="approver")
    created = await _create_pending_approval(setup)
    with _patch_agent2_send():
        response = setup["client"].post(
            f"/api/v1/approvals/{created['approval'].id}/approve",
            json={"comments": "OK"},
        )
    assert response.status_code == 200
    assert response.json()["approval"]["approver_id"] == str(approver_id)


@pytest.mark.asyncio
async def test_client_cannot_override_approver_id_on_approve(api_setup) -> None:
    setup = api_setup
    approver_id = override_current_user(role="approver")
    created = await _create_pending_approval(setup)
    spoofed = uuid4()
    with _patch_agent2_send():
        response = setup["client"].post(
            f"/api/v1/approvals/{created['approval'].id}/approve",
            json={"comments": "OK", "approver_id": str(spoofed)},
            params={"approver_id": str(spoofed)},
        )
    assert response.status_code == 200
    assert response.json()["approval"]["approver_id"] == str(approver_id)
    assert response.json()["approval"]["approver_id"] != str(spoofed)


def test_unauthenticated_reject_returns_401(api_setup) -> None:
    _clear_auth()
    response = api_setup["client"].post(
        f"/api/v1/approvals/{uuid4()}/reject",
        json={"comments": "nope"},
    )
    _assert_401(response)


@pytest.mark.asyncio
async def test_requester_reject_returns_403(api_setup) -> None:
    setup = api_setup
    override_current_user(role="requester")
    created = await _create_pending_approval(setup)
    response = setup["client"].post(
        f"/api/v1/approvals/{created['approval'].id}/reject",
        json={"comments": "Should fail"},
    )
    _assert_403(response)


@pytest.mark.asyncio
async def test_approver_reject_success(api_setup) -> None:
    setup = api_setup
    override_current_user(role="approver")
    created = await _create_pending_approval(setup)
    with _patch_agent2_send():
        response = setup["client"].post(
            f"/api/v1/approvals/{created['approval'].id}/reject",
            json={"comments": "Rejected"},
        )
    assert response.status_code == 200
    assert response.json()["decision"] == ApprovalStatus.REJECTED.value


@pytest.mark.asyncio
async def test_admin_reject_success(api_setup) -> None:
    setup = api_setup
    override_current_user(role="admin")
    created = await _create_pending_approval(setup)
    with _patch_agent2_send():
        response = setup["client"].post(
            f"/api/v1/approvals/{created['approval'].id}/reject",
            json={"comments": "Admin rejected"},
        )
    assert response.status_code == 200
    assert response.json()["decision"] == ApprovalStatus.REJECTED.value


@pytest.mark.asyncio
async def test_already_decided_approval_returns_409(api_setup) -> None:
    setup = api_setup
    override_current_user(role="approver")
    created = await _create_pending_approval(setup)
    first = setup["client"].post(
        f"/api/v1/approvals/{created['approval'].id}/approve",
        json={"comments": "Once"},
    )
    assert first.status_code == 200
    retry = setup["client"].post(
        f"/api/v1/approvals/{created['approval'].id}/approve",
        json={"comments": "Again"},
    )
    assert retry.status_code == 409
    assert retry.json()["detail"] == ALREADY_DECIDED_DETAIL


# --- EXCEPTIONS ---


def test_unauthenticated_resolve_exception_returns_401(api_setup) -> None:
    _clear_auth()
    response = api_setup["client"].post(
        f"/api/v1/exceptions/{uuid4()}/resolve",
        json={"resolution_notes": "fix"},
    )
    _assert_401(response)


@pytest.mark.asyncio
async def test_authenticated_resolve_exception_existing_behavior(api_setup) -> None:
    setup = api_setup
    override_current_user(role="requester")
    created = await _create_open_exception(setup)
    response = setup["client"].post(
        f"/api/v1/exceptions/{created['exception'].id}/resolve",
        json={"resolution_notes": "Fixed the issue"},
    )
    assert response.status_code == 200
    assert response.json()["exception"]["status"] == "resolved"


def test_unauthenticated_retry_exception_returns_401(api_setup) -> None:
    _clear_auth()
    response = api_setup["client"].post(
        f"/api/v1/exceptions/{uuid4()}/retry",
        json={"notes": "retry"},
    )
    _assert_401(response)


@pytest.mark.asyncio
async def test_authenticated_retry_exception_existing_behavior(api_setup) -> None:
    setup = api_setup
    override_current_user(role="requester")
    created = await _create_open_exception(setup)
    response = setup["client"].post(
        f"/api/v1/exceptions/{created['exception'].id}/retry",
        json={"notes": "Retry now"},
    )
    assert response.status_code == 200
    stage = await setup["orchestrator"].get_current_stage(created["process"].id)
    assert stage is WorkflowStage.DISCOVERING


def test_unauthenticated_fail_exception_returns_401(api_setup) -> None:
    _clear_auth()
    response = api_setup["client"].post(
        f"/api/v1/exceptions/{uuid4()}/fail",
        json={"resolution_notes": "fail"},
    )
    _assert_401(response)


@pytest.mark.asyncio
async def test_authenticated_fail_exception_existing_behavior(api_setup) -> None:
    setup = api_setup
    override_current_user(role="requester")
    created = await _create_open_exception(setup)
    response = setup["client"].post(
        f"/api/v1/exceptions/{created['exception'].id}/fail",
        json={"resolution_notes": "Cannot recover"},
    )
    assert response.status_code == 200
    assert response.json()["exception"]["status"] == "ignored"


# --- READS ---


def test_unauthenticated_process_list_returns_401(api_setup) -> None:
    _clear_auth()
    _assert_401(api_setup["client"].get("/api/v1/processes"))


def test_authenticated_process_list_success(api_setup) -> None:
    override_current_user(role="requester")
    _create_process(api_setup["client"])
    response = api_setup["client"].get("/api/v1/processes")
    assert response.status_code == 200
    assert len(response.json()) >= 1


def test_unauthenticated_approval_list_returns_401(api_setup) -> None:
    _clear_auth()
    _assert_401(api_setup["client"].get("/api/v1/approvals"))


def test_authenticated_approval_list_success(api_setup) -> None:
    override_current_user(role="requester")
    response = api_setup["client"].get("/api/v1/approvals")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_unauthenticated_exception_list_returns_401(api_setup) -> None:
    _clear_auth()
    _assert_401(api_setup["client"].get("/api/v1/exceptions"))


def test_authenticated_exception_list_success(api_setup) -> None:
    override_current_user(role="requester")
    response = api_setup["client"].get("/api/v1/exceptions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_unauthenticated_audit_list_returns_401(api_setup) -> None:
    _clear_auth()
    _assert_401(api_setup["client"].get("/api/v1/audit"))


def test_authenticated_audit_list_success(api_setup) -> None:
    override_current_user(role="requester")
    response = api_setup["client"].get("/api/v1/audit")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


# --- AUTH ROUTES ---


def test_auth_me_requires_authentication(api_setup) -> None:
    _clear_auth()
    _assert_401(api_setup["client"].get("/api/v1/auth/me"))


def test_auth_approver_check_requires_authentication(api_setup) -> None:
    _clear_auth()
    _assert_401(api_setup["client"].get("/api/v1/auth/approver-check"))


def test_requester_fails_approver_check(api_setup) -> None:
    override_current_user(role="requester")
    _assert_403(api_setup["client"].get("/api/v1/auth/approver-check"))


def test_approver_passes_approver_check(api_setup) -> None:
    override_current_user(role="approver")
    response = api_setup["client"].get("/api/v1/auth/approver-check")
    assert response.status_code == 200
    assert response.json()["role"] == "approver"


def test_admin_passes_approver_check(api_setup) -> None:
    override_current_user(role="admin")
    response = api_setup["client"].get("/api/v1/auth/approver-check")
    assert response.status_code == 200
    assert response.json()["role"] == "admin"


# --- SECURITY ---


def test_jwt_sub_maps_to_authenticated_identity_via_created_by(api_setup) -> None:
    """Authenticated identity is always CurrentUser.id, never client-supplied fields."""
    identity = override_current_user(role="requester", user_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"))
    body = _create_process(api_setup["client"])
    assert body["created_by"] == str(identity)
