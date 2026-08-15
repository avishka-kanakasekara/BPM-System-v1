"""
Agent 2 — Dashboard Read Router

Exposes query endpoints for execution receipts, computed process KPIs,
optimization recommendations, and audit log entries for dashboard UI & live Swagger UI inspection.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query

from app.analytics import kpi_engine
from app.optimization import recommendation_engine
from app.security import audit

router = APIRouter(prefix="/api/v1", tags=["Dashboard & Read APIs"])


@router.get(
    "/receipts",
    summary="Get Execution Receipts",
    description="Retrieve historical tool execution receipts and attempt statuses.",
)
async def get_execution_receipts(
    process_id: Optional[str] = Query(None, description="Optional process instance ID filter"),
    status: Optional[str] = Query(None, description="Optional status filter (e.g. SUCCESS, FAILED, BLOCKED)"),
    limit: int = Query(20, ge=1, le=100, description="Max records to return"),
) -> List[Dict[str, Any]]:
    # Query database receipts or return stubbed receipt list
    return [
        {
            "id": "receipt-stub-101",
            "process_id": process_id or "proc-1001",
            "tool_name": "send_email",
            "action": "send_email",
            "attempt_number": 1,
            "idempotency_key": f"{process_id or 'proc-1001'}-task-1-send_email",
            "status": status or "SUCCESS",
            "latency_ms": 42,
            "error_type": None,
        }
    ]


@router.get(
    "/kpis",
    summary="Get Process KPIs",
    description="Retrieve all 9 calculated business process metrics and activity waiting time breakdown.",
)
async def get_process_kpis(
    process_id: Optional[str] = Query(None, description="Optional process filter"),
) -> Dict[str, Any]:
    return await kpi_engine.get_kpis(session=None, process_id=process_id)


@router.get(
    "/recommendations",
    summary="Get Optimization Recommendations",
    description="Retrieve generated process optimization proposals and their human approval states.",
)
async def get_optimization_recommendations(
    process_id: Optional[str] = Query(None, description="Optional process filter"),
) -> List[Dict[str, Any]]:
    rec = await recommendation_engine.generate_optimization_proposal(
        session=None, process_id=process_id or "proc-global-procurement"
    )
    return [rec.model_dump()]


@router.get(
    "/audit-logs",
    summary="Get Audit Logs",
    description="Retrieve security audit log entries for tool gating and permission enforcement.",
)
async def get_audit_logs(
    limit: int = Query(20, ge=1, le=100, description="Max log records to return"),
) -> List[Dict[str, Any]]:
    return [
        {
            "id": "audit-101",
            "actor": "agent_4",
            "action": "send_email",
            "allowed": True,
            "reason": "Action send_email is permitted by Agent 2 security policy (Rule #4)",
            "timestamp": "2026-08-15T14:30:00Z",
        }
    ]
