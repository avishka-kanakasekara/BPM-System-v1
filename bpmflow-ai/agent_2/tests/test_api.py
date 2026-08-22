"""
Agent 2 — FastAPI Endpoint Integration & Round-Trip Tests

Tests:
1. Health and root endpoints.
2. Inbound POST /api/v1/messages round-trip execution.
3. GET /api/v1/receipts, /api/v1/kpis, /api/v1/recommendations, /api/v1/audit-logs.
4. Human Governance Gate endpoints (POST approve & reject recommendations).
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import auth

client = TestClient(app)


def test_root_and_health_endpoints():
    r1 = client.get("/")
    assert r1.status_code == 200
    assert r1.json()["status"] == "running"

    r2 = client.get("/health")
    assert r2.status_code == 200
    assert r2.json()["status"] == "healthy"

    r3 = client.get("/readiness")
    assert r3.status_code == 200
    assert r3.json()["status"] == "ready"


def test_inbound_messages_roundtrip():
    token = auth.create_access_token({"sub": "agent_4", "role": "orchestrator"})
    headers = {"Authorization": f"Bearer {token}"}

    msg_payload = {
        "message_id": "msg-api-test-101",
        "process_id": "proc-api-1001",
        "trace_id": "trace-api-1001",
        "sender": "agent_4",
        "receiver": "agent_2",
        "task_type": "EXECUTE_TASK",
        "payload": {
            "task_id": "task-api-2002",
            "task_title": "Send Finance Approval Reminder",
            "assigned_role": "finance_officer",
            "assigned_to": "henry.taylor@acmeglobal.com",
            "parameters": {
                "recipient": "henry.taylor@acmeglobal.com",
                "subject": "Approval Pending: Purchase Request #1001",
                "body": "Please review pending purchase request #1001.",
                "process_id": "proc-api-1001",
                "task_id": "task-api-2002",
                "recipient_role": "finance_officer",
            },
        },
        "confidence": 1.0,
        "status": "AUTHORIZED",
    }

    res = client.post("/api/v1/messages", json=msg_payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "EXECUTION_RESULT"
    assert data["sender"] == "agent_2"
    assert data["payload"]["total_score"] > 0.0


def test_read_endpoints():
    r_receipts = client.get("/api/v1/receipts")
    assert r_receipts.status_code == 200
    assert isinstance(r_receipts.json(), list)

    r_kpis = client.get("/api/v1/kpis")
    assert r_kpis.status_code == 200
    kpis = r_kpis.json()
    assert "average_cycle_time" in kpis
    assert "bottleneck_task" in kpis

    r_recs = client.get("/api/v1/recommendations")
    assert r_recs.status_code == 200
    recs = r_recs.json()
    assert len(recs) > 0
    assert recs[0]["status"] == "PENDING_APPROVAL"

    r_audit = client.get("/api/v1/audit-logs")
    assert r_audit.status_code == 200
    assert isinstance(r_audit.json(), list)


def test_human_governance_gate():
    rec_id = "opt-test-999"
    decision = {"user_id": "laura.white@acmeglobal.com", "notes": "Approved for viva demo"}

    # Approve recommendation
    r_app = client.post(f"/api/v1/recommendations/{rec_id}/approve", json=decision)
    assert r_app.status_code == 200
    data_app = r_app.json()
    assert data_app["status"] == "APPROVED"
    assert data_app["approved_by"] == "laura.white@acmeglobal.com"

    # Reject recommendation
    r_rej = client.post(f"/api/v1/recommendations/{rec_id}/reject", json=decision)
    assert r_rej.status_code == 200
    data_rej = r_rej.json()
    assert data_rej["status"] == "REJECTED"
    assert data_rej["rejected_by"] == "laura.white@acmeglobal.com"
