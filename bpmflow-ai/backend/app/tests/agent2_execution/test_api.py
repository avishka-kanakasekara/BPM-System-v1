"""
Agent 2 — monolith HTTP integration tests.

Legacy standalone Agent 2 FastAPI entry (main.py / POST /messages) was removed;
all routes mount on the BPMFlow monolith at /api/v1/agent2/*.
"""

import pytest
from fastapi.testclient import TestClient

from app.agents.agent2_execution.config import settings as agent2_settings
from app.core.security import get_current_user
from app.main import app
from app.tests.auth_helpers import override_current_user

client = TestClient(app)


@pytest.fixture(autouse=True)
def _offline_gemini_for_api_tests(monkeypatch):
    monkeypatch.setattr(agent2_settings, "GEMINI_OFFLINE", True)


@pytest.fixture(autouse=True)
def _auth_as_requester():
    override_current_user(role="requester")
    yield
    app.dependency_overrides.pop(get_current_user, None)


def test_root_and_health_endpoints():
    r1 = client.get("/")
    assert r1.status_code == 200
    assert r1.json()["status"] == "running"

    r2 = client.get("/health/live")
    assert r2.status_code == 200
    assert r2.json()["status"] == "alive"

    r3 = client.get("/health/deps")
    assert r3.status_code in (200, 503)
    body = r3.json()
    assert "dependencies" in body or "ready" in body


def test_read_endpoints():
    r_receipts = client.get("/api/v1/agent2/receipts")
    assert r_receipts.status_code == 200
    assert isinstance(r_receipts.json(), list)

    r_kpis = client.get("/api/v1/agent2/kpis")
    assert r_kpis.status_code == 200
    kpis = r_kpis.json()
    assert "average_cycle_time" in kpis
    assert "bottleneck_task" in kpis

    r_recs = client.get("/api/v1/agent2/recommendations")
    assert r_recs.status_code == 200
    recs = r_recs.json()
    assert len(recs) > 0
    assert recs[0]["status"] == "PENDING_APPROVAL"

    r_audit = client.get("/api/v1/agent2/audit-logs")
    assert r_audit.status_code == 200
    assert isinstance(r_audit.json(), list)


def test_human_governance_gate():
    override_current_user(role="approver")
    gov_client = TestClient(app)

    rec_id = "opt-test-999"
    decision = {"user_id": "laura.white@acmeglobal.com", "notes": "Approved for viva demo"}

    r_app = gov_client.post(f"/api/v1/agent2/recommendations/{rec_id}/approve", json=decision)
    assert r_app.status_code == 200
    data_app = r_app.json()
    assert data_app["status"] == "APPROVED"
    assert data_app["approved_by"] == "laura.white@acmeglobal.com"

    r_rej = gov_client.post(f"/api/v1/agent2/recommendations/{rec_id}/reject", json=decision)
    assert r_rej.status_code == 200
    data_rej = r_rej.json()
    assert data_rej["status"] == "REJECTED"
    assert data_rej["rejected_by"] == "laura.white@acmeglobal.com"

    app.dependency_overrides.pop(get_current_user, None)
