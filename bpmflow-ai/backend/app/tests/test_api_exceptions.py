"""API tests for EXCEPTION endpoints. No live Supabase database is required."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.agents.agent4_orchestrator.constants import (
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    WorkflowStage,
)
from app.agents.agent4_orchestrator.exception_repository import InMemoryExceptionRepository
from app.agents.agent4_orchestrator.exception_service import ExceptionService
from app.agents.agent4_orchestrator.repository import InMemoryProcessRepository
from app.agents.agent4_orchestrator.service import OrchestratorService
from app.api.v1.deps import get_exception_repository, get_exception_service
from app.main import app
from app.tests.auth_helpers import override_current_user


@pytest.fixture
def exception_setup():
    override_current_user(role="requester")
    process_repo = InMemoryProcessRepository()
    exception_repo = InMemoryExceptionRepository()
    orchestrator = OrchestratorService(repository=process_repo)
    exception_service = ExceptionService(
        orchestrator=orchestrator,
        repository=exception_repo,
    )

    async def override_exception_repository() -> InMemoryExceptionRepository:
        return exception_repo

    async def override_exception_service() -> ExceptionService:
        return exception_service

    app.dependency_overrides[get_exception_repository] = override_exception_repository
    app.dependency_overrides[get_exception_service] = override_exception_service

    yield {
        "client": TestClient(app),
        "process_repo": process_repo,
        "exception_repo": exception_repo,
        "orchestrator": orchestrator,
        "exception_service": exception_service,
    }

    app.dependency_overrides.clear()


async def _create_exception(
    setup,
    *,
    stage: WorkflowStage = WorkflowStage.WORKFLOW_EXECUTION,
    description: str = "System issue",
) -> dict:
    process = await setup["process_repo"].insert_process(
        name="Exception process",
        process_type="procurement",
    )
    await setup["process_repo"].update_process_stage(process.id, stage)
    record = await setup["exception_service"].create_exception(
        process.id,
        description=description,
        severity=ExceptionSeverity.HIGH,
        exception_type=ExceptionType.SYSTEM_ERROR,
    )
    return {"process": process, "exception": record}


@pytest.mark.asyncio
async def test_list_exceptions(exception_setup) -> None:
    setup = exception_setup
    await _create_exception(setup, description="First issue")
    await _create_exception(setup, description="Second issue")

    response = setup["client"].get("/api/v1/exceptions")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    descriptions = {item["description"] for item in body}
    assert descriptions == {"First issue", "Second issue"}
    for item in body:
        assert item["status"] == ExceptionStatus.OPEN.value


@pytest.mark.asyncio
async def test_list_exceptions_filtered_by_status(exception_setup) -> None:
    setup = exception_setup
    open_item = await _create_exception(setup, description="Still open")
    resolved_item = await _create_exception(setup, description="Will resolve")
    await setup["exception_service"].resolve_exception(
        resolved_item["exception"].id,
        resolution_notes="Fixed",
    )

    response = setup["client"].get(
        "/api/v1/exceptions",
        params={"status": ExceptionStatus.OPEN.value},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(open_item["exception"].id)
    assert body[0]["status"] == ExceptionStatus.OPEN.value


def test_invalid_status_filter_returns_422(exception_setup) -> None:
    response = exception_setup["client"].get(
        "/api/v1/exceptions",
        params={"status": "failed"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_exception(exception_setup) -> None:
    setup = exception_setup
    created = await _create_exception(setup)

    response = setup["client"].get(f"/api/v1/exceptions/{created['exception'].id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(created["exception"].id)
    assert body["process_id"] == str(created["process"].id)
    assert body["status"] == ExceptionStatus.OPEN.value


def test_get_unknown_exception_returns_404(exception_setup) -> None:
    response = exception_setup["client"].get(f"/api/v1/exceptions/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Exception not found"


@pytest.mark.asyncio
async def test_resolve_open_exception(exception_setup) -> None:
    setup = exception_setup
    created = await _create_exception(setup, stage=WorkflowStage.INVOICE_MATCHING)

    response = setup["client"].post(
        f"/api/v1/exceptions/{created['exception'].id}/resolve",
        json={"resolution_notes": "Evidence was reviewed and the issue was resolved."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["exception"]["status"] == ExceptionStatus.RESOLVED.value
    assert (
        body["exception"]["resolution_notes"]
        == "Evidence was reviewed and the issue was resolved."
    )
    assert body["exception"]["resolved_at"] is not None
    stage = await setup["orchestrator"].get_current_stage(created["process"].id)
    assert stage is WorkflowStage.EXCEPTION
    assert stage is not WorkflowStage.COMPLETED


@pytest.mark.asyncio
async def test_retry_eligible_exception(exception_setup) -> None:
    setup = exception_setup
    created = await _create_exception(setup)

    response = setup["client"].post(
        f"/api/v1/exceptions/{created['exception'].id}/retry",
        json={"notes": "Retry after correcting the input."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["exception"]["id"] == str(created["exception"].id)
    assert body["exception"]["status"] == ExceptionStatus.IN_PROGRESS.value
    assert "Retry after correcting the input." in (
        body["exception"]["resolution_notes"] or ""
    )
    stage = await setup["orchestrator"].get_current_stage(created["process"].id)
    assert stage is WorkflowStage.DISCOVERING
    assert stage is not WorkflowStage.COMPLETED


@pytest.mark.asyncio
async def test_second_retry_is_rejected(exception_setup) -> None:
    setup = exception_setup
    created = await _create_exception(setup)
    first = setup["client"].post(
        f"/api/v1/exceptions/{created['exception'].id}/retry",
        json={"notes": "First retry"},
    )
    assert first.status_code == 200

    second = setup["client"].post(
        f"/api/v1/exceptions/{created['exception'].id}/retry",
        json={"notes": "Second retry"},
    )

    assert second.status_code == 409
    assert second.json()["detail"] == "Invalid exception action"


@pytest.mark.asyncio
async def test_fail_eligible_exception_maps_to_ignored(exception_setup) -> None:
    setup = exception_setup
    created = await _create_exception(setup)

    response = setup["client"].post(
        f"/api/v1/exceptions/{created['exception'].id}/fail",
        json={"resolution_notes": "The issue cannot be recovered."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["exception"]["status"] == ExceptionStatus.IGNORED.value
    assert body["exception"]["resolution_notes"] == "The issue cannot be recovered."
    assert body["exception"]["resolved_at"] is not None
    stage = await setup["orchestrator"].get_current_stage(created["process"].id)
    assert stage is WorkflowStage.EXCEPTION
    assert stage is not WorkflowStage.COMPLETED


@pytest.mark.asyncio
async def test_terminal_exception_cannot_be_retried(exception_setup) -> None:
    setup = exception_setup
    created = await _create_exception(setup)
    resolved = setup["client"].post(
        f"/api/v1/exceptions/{created['exception'].id}/resolve",
        json={"resolution_notes": "Resolved"},
    )
    assert resolved.status_code == 200

    response = setup["client"].post(
        f"/api/v1/exceptions/{created['exception'].id}/retry",
        json={"notes": "Try again"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Invalid exception action"


@pytest.mark.asyncio
async def test_terminal_exception_cannot_be_resolved_again(exception_setup) -> None:
    setup = exception_setup
    created = await _create_exception(setup)
    first = setup["client"].post(
        f"/api/v1/exceptions/{created['exception'].id}/resolve",
        json={"resolution_notes": "Fixed"},
    )
    assert first.status_code == 200

    second = setup["client"].post(
        f"/api/v1/exceptions/{created['exception'].id}/resolve",
        json={"resolution_notes": "Fixed again"},
    )

    assert second.status_code == 409
    assert second.json()["detail"] == "Invalid exception action"


@pytest.mark.asyncio
async def test_retry_does_not_bypass_state_machine(exception_setup) -> None:
    setup = exception_setup
    created = await _create_exception(setup, stage=WorkflowStage.DRAFT)

    response = setup["client"].post(
        f"/api/v1/exceptions/{created['exception'].id}/retry",
        json={"notes": "Retry from wrong stage"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Invalid exception action"
    stage = await setup["orchestrator"].get_current_stage(created["process"].id)
    assert stage is WorkflowStage.DRAFT
    assert stage is not WorkflowStage.COMPLETED
