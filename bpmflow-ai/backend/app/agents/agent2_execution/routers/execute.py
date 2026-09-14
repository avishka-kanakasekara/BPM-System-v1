"""
Agent 2 — Execution & dashboard API routes.

All mutating executions route through the Agent 2 cognitive pipeline after
server-side Agent 4 stage validation. No direct tool-handler bypass exists.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.agent.planner_fallback import FULL_TASK_SUITE_TOOL, is_full_task_suite
from app.agents.agent2_execution.analytics import kpi_engine
from app.agents.agent2_execution.config import settings as agent2_settings
from app.agents.agent2_execution.database.ids import parse_uuid
from app.agents.agent2_execution.database.models import AuditLog, ExecutionReceipt, Failure
from app.agents.agent2_execution.database.session import get_db_session
from app.agents.agent2_execution.execution.idempotency import generate_idempotency_key
from app.agents.agent2_execution.execution.service import run_authorized_pipeline
from app.agents.agent2_execution.routers.read import load_receipt_detail_rest
from app.agents.agent2_execution.security.execution_authorization import (
    authorize_retry,
    authorize_tool_execution,
)
from app.agents.agent2_execution.tools.email_provider import email_configured, email_dry_run_enabled
from app.agents.agent2_execution.tools.metadata import list_tool_capabilities
from app.agents.agent4_orchestrator.exceptions import ProcessNotFoundError
from app.agents.agent4_orchestrator.repository import ProcessRepository
from app.api.v1.deps import get_process_repository
from app.core.config import settings as core_settings
from app.core.security import get_current_user
from app.core.tenancy import deny_foreign_process
from app.schemas.auth import CurrentUser

logger = logging.getLogger("agent_2.routers.execute")

router = APIRouter(prefix="/agent2", tags=["Agent 2 — Execution"])


class ExecuteToolRequest(BaseModel):
    process_id: str = Field(..., description="Process instance UUID")
    task_id: str = Field(..., description="Task UUID")
    tool_name: str | None = Field(
        default=None,
        description="Legacy single-tool name. Forbidden: __full_task_suite__. Prefer workflow_step_id.",
    )
    parameters: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = Field(default="", description="Client idempotency / correlation id")
    process_context_ref: str | None = Field(
        default=None,
        description="Canonical ProcessContext process_id; Agent 2 does not own the context.",
    )
    workflow_plan_id: str | None = None
    workflow_step_id: str | None = None


class RetryExecutionRequest(BaseModel):
    process_id: str
    task_id: str
    tool_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)


def _receipt_dict(r: ExecutionReceipt, explanation: dict[str, Any] | None = None) -> dict[str, Any]:
    out = {
        "execution_id": str(r.id),
        "process_id": str(r.process_id),
        "task_id": str(r.task_id),
        "status": r.status,
        "receipt_status": r.status,
        "tool_name": r.tool_name,
        "action": r.action,
        "attempt": r.attempt_number,
        "attempt_number": r.attempt_number,
        "idempotency_key": r.idempotency_key,
        "started_at": r.started_at.isoformat() if r.started_at else "",
        "completed_at": r.completed_at.isoformat() if r.completed_at else "",
        "latency_ms": r.latency_ms or 0,
        "result": r.result or {},
        "error_type": r.error_type,
        "error_message": r.error_message,
        "created_at": r.created_at.isoformat() if r.created_at else "",
    }
    if explanation:
        out["execution_explanation"] = explanation
    return out


async def _load_receipt(
    session: AsyncSession | None, receipt_id: str
) -> ExecutionReceipt | None:
    if session is None:
        return None
    try:
        res = await session.execute(
            select(ExecutionReceipt).where(ExecutionReceipt.id == parse_uuid(receipt_id))
        )
        return res.scalar_one_or_none()
    except Exception:
        return None


def _email_mode() -> dict[str, Any]:
    dry = bool(agent2_settings.EMAIL_DRY_RUN or core_settings.EMAIL_DRY_RUN)
    provider = (agent2_settings.EMAIL_PROVIDER or core_settings.EMAIL_PROVIDER or "smtp").lower()
    return {
        "mode": "DRY_RUN" if dry else "LIVE",
        "provider": provider,
        "configured": email_configured(),
        "dry_run": dry or email_dry_run_enabled(),
    }


@router.get("/health", summary="Agent 2 dependency health")
async def agent2_health(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    _ = current_user
    return {
        "agent": "agent_2",
        "email": _email_mode(),
        "scheduler": {"poll_seconds": 30, "status": "running"},
        "gemini_offline": bool(agent2_settings.GEMINI_OFFLINE),
    }


@router.get("/tools", summary="List Agent 2 tool capabilities")
async def get_tools(
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    _ = current_user
    return list_tool_capabilities()


@router.get("/dashboard", summary="Agent 2 execution dashboard metrics")
async def get_dashboard(
    process_id: str | None = Query(None),
    session: AsyncSession | None = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    _ = current_user
    receipts: list[dict[str, Any]] = []
    audit_count = 0
    exception_count = 0

    if session is not None:
        stmt = select(ExecutionReceipt).order_by(ExecutionReceipt.created_at.desc()).limit(500)
        if process_id:
            stmt = stmt.where(ExecutionReceipt.process_id == parse_uuid(process_id))
        res = await session.execute(stmt)
        receipts = [_receipt_dict(r) for r in res.scalars().all()]
        audit_res = await session.execute(select(func.count()).select_from(AuditLog))
        audit_count = int(audit_res.scalar() or 0)
        fail_stmt = select(func.count()).select_from(Failure).where(
            Failure.resolution_status == "OPEN"
        )
        fail_res = await session.execute(fail_stmt)
        exception_count = int(fail_res.scalar() or 0)
    else:
        try:
            from app.core.supabase_rest import rest_select, supabase_rest_configured

            if supabase_rest_configured():
                params: dict[str, str] = {
                    "select": "id,status,latency_ms,tool_name,created_at,process_id",
                    "order": "created_at.desc",
                    "limit": "500",
                }
                if process_id:
                    params["process_id"] = f"eq.{process_id}"
                receipts = [
                    {
                        "execution_id": str(r.get("id") or ""),
                        "status": r.get("status") or "",
                        "latency_ms": r.get("latency_ms") or 0,
                        "tool_name": r.get("tool_name") or "",
                        "created_at": r.get("created_at") or "",
                    }
                    for r in rest_select("execution_receipts", params)
                ]
        except Exception as exc:
            logger.warning("dashboard_rest_fallback_failed", extra={"error": str(exc)})

    total = len(receipts)
    success = sum(1 for r in receipts if r.get("status") == "SUCCESS")
    failed = sum(1 for r in receipts if r.get("status") == "FAILED")
    blocked = sum(1 for r in receipts if r.get("status") == "BLOCKED")
    retrying = sum(1 for r in receipts if r.get("status") == "RETRYING")
    latencies = [int(r.get("latency_ms") or 0) for r in receipts if r.get("latency_ms")]
    avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else 0.0
    tool_usage: dict[str, int] = {}
    for r in receipts:
        t = r.get("tool_name") or "unknown"
        tool_usage[t] = tool_usage.get(t, 0) + 1

    kpis = await kpi_engine.get_kpis(session=session, process_id=process_id)

    return {
        "agent": "agent_2",
        "status": "OPERATIONAL",
        "process_id": process_id,
        "dependencies": {"email": _email_mode()},
        "metrics": {
            "total_executions": total,
            "successful": success,
            "failed": failed,
            "blocked": blocked,
            "retrying": retrying,
            "success_rate": round(success / total, 4) if total else 0.0,
            "failure_rate": round(failed / total, 4) if total else 0.0,
            "average_latency_ms": avg_latency,
            "open_exceptions": exception_count,
            "audit_events": audit_count,
        },
        "tool_usage": tool_usage,
        "recent_executions": receipts[:15],
        "kpis": kpis,
        "health": "healthy" if failed == 0 or (success / max(total, 1)) >= 0.5 else "degraded",
    }


@router.get("/receipts/{receipt_id}", summary="Execution receipt detail")
async def get_receipt_detail(
    receipt_id: str,
    session: AsyncSession | None = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    _ = current_user
    row = await _load_receipt(session, receipt_id)
    if row is not None:
        detail = _receipt_dict(row)
    else:
        detail = load_receipt_detail_rest(receipt_id)
        if detail is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found")
    receipt_status = detail.get("status") or detail.get("receipt_status") or ""
    detail["authorization"] = {
        "agent4_authorized": True,
        "tool_guard": "ALLOWED" if receipt_status != "BLOCKED" else "DENIED",
    }
    result_payload = detail.get("result") or {}
    if row is not None:
        result_payload = row.result or result_payload
    detail["plan_score"] = result_payload.get("plan_score") or {}
    return detail


@router.post("/execute", summary="Execute one authorized Agent 2 tool (legacy) or one WorkflowStep")
async def execute_tool_endpoint(
    payload: ExecuteToolRequest,
    session: AsyncSession | None = Depends(get_db_session),
    repository: ProcessRepository = Depends(get_process_repository),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    tool_name = (payload.tool_name or payload.parameters.get("tool_name") or "").strip().lower()
    if is_full_task_suite(tool_name) or is_full_task_suite(str(payload.parameters.get("tool_name") or "")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "FULL_WORKFLOW_EXECUTION_FORBIDDEN",
                "message": "Agent 2 executes exactly one WorkflowStep. __full_task_suite__ is forbidden.",
            },
        )

    try:
        process = await repository.get_process(uuid.UUID(str(payload.process_id)))
        deny_foreign_process(process, current_user)
    except (ValueError, ProcessNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Process not found") from exc

    if payload.workflow_plan_id and payload.workflow_step_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "USE_WORKFLOW_STEP_EXECUTE",
                "message": (
                    "Use POST /api/v1/workflows/{workflow_plan_id}/steps/{workflow_step_id}/execute"
                ),
            },
        )

    if not tool_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "WORKFLOW_STEP_REQUIRED",
                "message": "Provide workflow_plan_id and workflow_step_id, or a single tool_name.",
            },
        )
    auth = await authorize_tool_execution(repository, payload.process_id, tool_name)
    if not auth.authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN if auth.error_code == "NOT_AUTHORIZED" else status.HTTP_404_NOT_FOUND,
            detail={"error": auth.error_code, "message": auth.message},
        )

    params = dict(payload.parameters)
    params.setdefault("process_id", payload.process_id)
    params.setdefault("task_id", payload.task_id)

    idem = payload.correlation_id.strip() or generate_idempotency_key(
        payload.process_id, payload.task_id, tool_name
    )

    logger.info(
        "agent2_execute_request",
        extra={
            "process_id": payload.process_id,
            "task_id": payload.task_id,
            "tool": tool_name,
            "user": current_user.email,
            "idempotency_key": idem,
        },
    )

    receipt, _score, explanation = await run_authorized_pipeline(
        process_id=payload.process_id,
        task_id=payload.task_id,
        tool_name=tool_name,
        parameters=params,
        session=session,
        correlation_id=payload.correlation_id,
        actor=f"user:{current_user.email or current_user.id}",
        idempotency_key=idem,
    )

    # Prefer persisted receipt when available
    persisted = await _load_receipt(session, str(receipt.id))
    if persisted is not None:
        receipt = persisted

    out = _receipt_dict(receipt, explanation)
    out["authorization"] = {
        "agent4_authorized": auth.stage != "READ_ONLY",
        "stage": auth.stage,
        "tool_guard": "ALLOWED" if receipt.status != "BLOCKED" else "DENIED",
    }
    if receipt.status == "BLOCKED":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "TOOL_GUARD_DENIED", "receipt": out},
        )
    return out


@router.post("/receipts/{receipt_id}/retry", summary="Retry a failed execution")
async def retry_execution(
    receipt_id: str,
    payload: RetryExecutionRequest,
    session: AsyncSession | None = Depends(get_db_session),
    repository: ProcessRepository = Depends(get_process_repository),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    auth = await authorize_retry(
        repository,
        session,
        receipt_id=receipt_id,
        process_id=payload.process_id,
        task_id=payload.task_id,
        tool_name=payload.tool_name,
    )
    if not auth.authorized:
        code = status.HTTP_403_FORBIDDEN
        if auth.error_code in {"RECEIPT_NOT_FOUND", "PROCESS_NOT_FOUND"}:
            code = status.HTTP_404_NOT_FOUND
        elif auth.error_code == "RETRY_LIMIT_EXCEEDED":
            code = status.HTTP_429_TOO_MANY_REQUESTS
        raise HTTPException(
            status_code=code,
            detail={"error": auth.error_code, "message": auth.message},
        )

    base_key = generate_idempotency_key(payload.process_id, payload.task_id, payload.tool_name)
    retry_key = f"{base_key}-retry-{uuid.uuid4().hex[:8]}"

    params = dict(payload.parameters)
    params.setdefault("process_id", payload.process_id)
    params.setdefault("task_id", payload.task_id)

    receipt, _score, explanation = await run_authorized_pipeline(
        process_id=payload.process_id,
        task_id=payload.task_id,
        tool_name=payload.tool_name.strip().lower(),
        parameters=params,
        session=session,
        actor=f"retry:{receipt_id}:user:{current_user.email or current_user.id}",
        idempotency_key=retry_key,
    )

    persisted = await _load_receipt(session, str(receipt.id))
    if persisted is not None:
        receipt = persisted

    out = _receipt_dict(receipt, explanation)
    out["retry_of"] = receipt_id
    out["idempotency_key"] = retry_key
    return out


@router.get("/exceptions", summary="List Agent 2 execution exceptions")
async def list_exceptions(
    process_id: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession | None = Depends(get_db_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    _ = current_user
    if session is None:
        return []

    stmt = select(Failure).order_by(Failure.created_at.desc()).offset(offset).limit(limit)
    if status_filter:
        stmt = stmt.where(Failure.resolution_status == status_filter.upper())
    res = await session.execute(stmt)
    rows = res.scalars().all()
    return [
        {
            "exception_id": str(r.id),
            "execution_receipt_id": str(r.execution_receipt_id) if r.execution_receipt_id else "",
            "task_id": str(r.task_id) if r.task_id else "",
            "category": r.failure_type,
            "severity": r.severity,
            "description": r.description,
            "status": r.resolution_status,
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "process_id": process_id or "",
        }
        for r in rows
    ]
