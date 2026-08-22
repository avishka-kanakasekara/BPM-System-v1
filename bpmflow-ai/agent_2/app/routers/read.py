"""
Agent 2 — Dashboard Read Router

Exposes query endpoints for execution receipts, computed process KPIs,
optimization recommendations, and audit log entries for dashboard UI & live Swagger UI inspection.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import kpi_engine
from app.database.ids import parse_uuid
from app.database.models import AuditLog, ExecutionReceipt, OptimizationRecommendation
from app.database.session import get_db_session
from app.optimization import recommendation_engine

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
    session: Optional[AsyncSession] = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    if session is None:
        return []

    stmt = select(ExecutionReceipt).order_by(ExecutionReceipt.created_at.desc()).limit(limit)

    if process_id:
        stmt = stmt.where(ExecutionReceipt.process_id == parse_uuid(process_id))

    if status:
        stmt = stmt.where(ExecutionReceipt.status == status)

    res = await session.execute(stmt)
    receipts = res.scalars().all()
    return [
        {
            "id": str(r.id),
            "process_id": str(r.process_id),
            "task_id": str(r.task_id),
            "tool_name": r.tool_name,
            "action": r.action,
            "attempt_number": r.attempt_number,
            "idempotency_key": r.idempotency_key,
            "status": r.status,
            "latency_ms": r.latency_ms,
            "error_type": r.error_type,
            "error_message": r.error_message,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        }
        for r in receipts
    ]


@router.get(
    "/kpis",
    summary="Get Process KPIs",
    description="Retrieve all 9 calculated business process metrics and activity waiting time breakdown.",
)
async def get_process_kpis(
    process_id: Optional[str] = Query(None, description="Optional process filter"),
    session: Optional[AsyncSession] = Depends(get_db_session),
) -> Dict[str, Any]:
    return await kpi_engine.get_kpis(session=session, process_id=process_id)


@router.get(
    "/recommendations",
    summary="Get Optimization Recommendations",
    description="Retrieve generated process optimization proposals and their human approval states.",
)
async def get_optimization_recommendations(
    process_id: Optional[str] = Query(None, description="Optional process filter"),
    session: Optional[AsyncSession] = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    if session is None:
        rec = await recommendation_engine.generate_optimization_proposal(
            session=None,
            process_id=process_id or "proc-global-procurement",
        )
        return [rec.model_dump()]

    stmt = select(OptimizationRecommendation).order_by(OptimizationRecommendation.created_at.desc())
    if process_id:
        stmt = stmt.where(OptimizationRecommendation.process_id == parse_uuid(process_id))

    res = await session.execute(stmt.limit(50))
    rows = res.scalars().all()
    if rows:
        return [
            {
                "id": str(r.id),
                "process_id": str(r.process_id),
                "recommendation_type": r.recommendation_type,
                "problem": r.problem,
                "root_cause": r.root_cause,
                "evidence": r.evidence or {},
                "baseline_metric": r.baseline_metric,
                "predicted_metric": r.predicted_metric,
                "improvement_percent": r.improvement_percent,
                "confidence": r.confidence,
                "risk": r.risk,
                "status": r.status,
                "approved_by": r.approved_by or "",
                "approved_at": r.approved_at.isoformat() if r.approved_at else "",
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ]

    rec = await recommendation_engine.generate_optimization_proposal(
        session=session,
        process_id=process_id or "00000000-0000-0000-0000-000000000000",
    )
    return [rec.model_dump()]


@router.get(
    "/audit-logs",
    summary="Get Audit Logs",
    description="Retrieve security audit log entries for tool gating and permission enforcement.",
)
async def get_audit_logs(
    limit: int = Query(20, ge=1, le=100, description="Max log records to return"),
    session: Optional[AsyncSession] = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    if session is None:
        return []

    stmt = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
    res = await session.execute(stmt)
    rows = res.scalars().all()
    return [
        {
            "id": str(r.id),
            "actor": r.actor,
            "agent": r.agent,
            "action": r.action,
            "allowed": r.allowed,
            "reason": r.reason,
            "payload": r.payload or {},
            "timestamp": r.timestamp.isoformat() if r.timestamp else "",
        }
        for r in rows
    ]
