"""
# MOCK: Stand-in for Agent 4 (Orchestrator, Coordination & Risk Analysis Agent), which does not exist yet.
# Swap this mock for the real Agent 4 service when built.
"""

import logging
import uuid
from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mock_agent4")

app = FastAPI(title="Mock Agent 4 — Orchestrator Stand-in")


@app.on_event("startup")
def startup_event():
    logger.info("⚠️ MOCK AGENT 4 — for development/demo only")


class ScenarioRequest(BaseModel):
    process_id: str = Field(default="proc-mock-1001", description="Process instance ID")
    task_id: str = Field(default="task-mock-2002", description="Task ID")
    recipient: str = Field(default="henry.taylor@acmeglobal.com", description="Recipient email")


@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "Mock Agent 4 Orchestrator",
        "notice": "⚠️ MOCK AGENT 4 — for development/demo only",
    }


@app.post("/api/v1/messages")
def receive_message_from_agent2(payload: dict):
    logger.info(f"Mock Agent 4 received message: {payload.get('message_id')} | type={payload.get('task_type')}")
    return {
        "status": "RECEIVED",
        "acknowledged": True,
        "message_id": payload.get("message_id"),
    }


@app.post("/api/v1/mock/scenario1-reminder")
def trigger_scenario1_reminder(req: ScenarioRequest):
    msg = {
        "message_id": f"msg-sc1-{uuid.uuid4().hex[:6]}",
        "process_id": req.process_id,
        "trace_id": f"trace-sc1-{uuid.uuid4().hex[:6]}",
        "sender": "agent_4",
        "receiver": "agent_2",
        "task_type": "EXECUTE_TASK",
        "payload": {
            "task_id": req.task_id,
            "task_title": "Send Finance Approval Reminder",
            "assigned_role": "finance_officer",
            "assigned_to": req.recipient,
            "elapsed_hours": 18.5,
            "sla_hours": 24.0,
            "parameters": {
                "recipient": req.recipient,
                "subject": f"Reminder: Finance Approval Pending for Request #{req.process_id}",
                "body": "Please review pending purchase request finance approval.",
                "process_id": req.process_id,
                "task_id": req.task_id,
                "recipient_role": "finance_officer",
            },
        },
        "confidence": 1.0,
        "status": "AUTHORIZED",
    }
    return {"scenario": "scenario1-reminder", "message": msg}


@app.post("/api/v1/mock/scenario2-smtp-timeout")
def trigger_scenario2_timeout(req: ScenarioRequest):
    msg = {
        "message_id": f"msg-sc2-{uuid.uuid4().hex[:6]}",
        "process_id": req.process_id,
        "trace_id": f"trace-sc2-{uuid.uuid4().hex[:6]}",
        "sender": "agent_4",
        "receiver": "agent_2",
        "task_type": "EXECUTE_TASK",
        "payload": {
            "task_id": req.task_id,
            "task_title": "Send Manager Approval Reminder (Simulated Timeout)",
            "assigned_role": "manager",
            "assigned_to": "frank.miller@acmeglobal.com",
            "inject_timeout": True,
            "parameters": {
                "recipient": "frank.miller@acmeglobal.com",
                "subject": "SLA Reminder: Manager Approval Required",
                "body": "Simulated timeout task payload.",
                "process_id": req.process_id,
                "task_id": req.task_id,
                "recipient_role": "manager",
            },
        },
        "confidence": 1.0,
        "status": "AUTHORIZED",
    }
    return {"scenario": "scenario2-smtp-timeout", "message": msg}


@app.post("/api/v1/mock/scenario3-optimization-pass")
def trigger_scenario3_optimization(req: ScenarioRequest):
    msg = {
        "message_id": f"msg-sc3-{uuid.uuid4().hex[:6]}",
        "process_id": req.process_id,
        "trace_id": f"trace-sc3-{uuid.uuid4().hex[:6]}",
        "sender": "agent_4",
        "receiver": "agent_2",
        "task_type": "ANALYZE_AND_OPTIMIZE",
        "payload": {
            "process_type": "procurement",
            "days_back": 30,
        },
        "confidence": 1.0,
        "status": "AUTHORIZED",
    }
    return {"scenario": "scenario3-optimization-pass", "message": msg}


@app.post("/api/v1/mock/scenario4-approve-recommendation")
def trigger_scenario4_approve_recommendation(recommendation_id: str):
    return {
        "scenario": "scenario4-approve-recommendation",
        "recommendation_id": recommendation_id,
        "approved_by": "laura.white@acmeglobal.com",
        "status": "APPROVED",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
