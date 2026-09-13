"""
Agent 2 — Execute API authorization and tools list tests.
"""

import uuid
from datetime import UTC
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.main import app
from app.tests.auth_helpers import override_current_user

client = TestClient(app)


@pytest.fixture
def mock_user_override():
    override_current_user(role="admin")
    yield
    app.dependency_overrides.pop(get_current_user, None)


def test_list_tools_endpoint(mock_user_override):
    res = client.get("/api/v1/agent2/tools")
    assert res.status_code == 200
    tools = res.json()
    assert len(tools) == 12
    names = {t["name"] for t in tools}
    assert "send_email" in names
    assert "create_po_draft" in names


def test_dashboard_endpoint(mock_user_override):
    res = client.get("/api/v1/agent2/dashboard")
    assert res.status_code == 200
    data = res.json()
    assert data["agent"] == "agent_2"
    assert "metrics" in data


def test_execute_rejects_without_workflow_execution(mock_user_override):
    process_id = str(uuid.uuid4())

    class FakeProcess:
        id = process_id
        current_stage = "DRAFT"

    mock_repo = AsyncMock()
    mock_repo.get_process = AsyncMock(return_value=FakeProcess())

    from app.api.v1.deps import get_process_repository

    app.dependency_overrides[get_process_repository] = lambda: mock_repo
    try:
        res = client.post(
            "/api/v1/agent2/execute",
            json={
                "process_id": process_id,
                "task_id": str(uuid.uuid4()),
                "tool_name": "send_email",
                "parameters": {
                    "recipient": "frank.miller@acmeglobal.com",
                    "subject": "Hi",
                    "body": "Test",
                },
            },
        )
        assert res.status_code == 403
        assert res.json()["detail"]["error"] == "NOT_AUTHORIZED"
    finally:
        app.dependency_overrides.pop(get_process_repository, None)


def test_receipt_detail_rest_fallback_when_db_unavailable(mock_user_override):
    receipt_id = "5e5ae40b-4251-46a9-b740-19f39361c85d"
    fake_detail = {
        "execution_id": receipt_id,
        "id": receipt_id,
        "process_id": str(uuid.uuid4()),
        "task_id": str(uuid.uuid4()),
        "status": "SUCCESS",
        "receipt_status": "SUCCESS",
        "tool_name": "send_email",
        "action": "send_email",
        "attempt": 1,
        "attempt_number": 1,
        "idempotency_key": "test-key",
        "started_at": "",
        "completed_at": "",
        "latency_ms": 42,
        "result": {"status": "DRY_RUN"},
        "error_type": None,
        "error_message": None,
        "created_at": "2026-01-01T00:00:00Z",
    }

    from app.agents.agent2_execution.database.session import get_db_session

    async def _no_db():
        yield None

    app.dependency_overrides[get_db_session] = _no_db
    try:
        with patch(
            "app.agents.agent2_execution.routers.execute.load_receipt_detail_rest",
            return_value=fake_detail,
        ):
            res = client.get(f"/api/v1/agent2/receipts/{receipt_id}")
        assert res.status_code == 200
        body = res.json()
        assert body["execution_id"] == receipt_id
        assert body["tool_name"] == "send_email"
        assert body["authorization"]["tool_guard"] == "ALLOWED"
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def test_read_only_tool_allowed_without_execution_stage(mock_user_override):
    process_id = str(uuid.uuid4())

    class FakeProcess:
        id = process_id
        current_stage = "DRAFT"

    mock_repo = AsyncMock()
    mock_repo.get_process = AsyncMock(return_value=FakeProcess())

    from app.api.v1.deps import get_process_repository

    app.dependency_overrides[get_process_repository] = lambda: mock_repo
    with patch(
        "app.agents.agent2_execution.routers.execute.run_authorized_pipeline",
        new_callable=AsyncMock,
    ) as mock_pipeline:
        from datetime import datetime

        from app.agents.agent2_execution.agent.decision_engine import PlanScoreBreakdown
        from app.agents.agent2_execution.database.models import ExecutionReceipt

        receipt = ExecutionReceipt(
            id=uuid.uuid4(),
            process_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            agent_id="agent_2",
            tool_name="calculate_kpi",
            action="calculate_kpi",
            attempt_number=1,
            idempotency_key="k",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            status="SUCCESS",
            result={"kpi": 1.0},
            latency_ms=10,
        )
        mock_pipeline.return_value = (
            receipt,
            PlanScoreBreakdown(1.0, 1, 1, 1, 1, 1, {}),
            {"receipt_status": "SUCCESS"},
        )
        try:
            res = client.post(
                "/api/v1/agent2/execute",
                json={
                    "process_id": process_id,
                    "task_id": str(uuid.uuid4()),
                    "tool_name": "calculate_kpi",
                    "parameters": {"process_id": process_id, "process_type": "procurement"},
                },
            )
            assert res.status_code == 200
            assert res.json()["status"] == "SUCCESS"
            mock_pipeline.assert_called_once()
        finally:
            app.dependency_overrides.pop(get_process_repository, None)
