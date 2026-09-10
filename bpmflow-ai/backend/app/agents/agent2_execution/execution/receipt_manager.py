"""
Agent 2 — Receipt & Workflow Event Manager

Writes execution_receipts records and matching workflow_events records for every tool attempt (success or failure).
Falls back to PostgREST when the SQLAlchemy session is unavailable.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.database.ids import parse_uuid
from app.agents.agent2_execution.database.models import EmailEvent, ExecutionReceipt, WorkflowEvent
from app.agents.agent2_execution.database.persistence import (
    ensure_process_instance,
    ensure_task,
    merge_process_metadata,
)

logger = logging.getLogger("agent_2.execution.receipt_manager")


def _ensure_task_rest(process_id: str, task_id: str) -> bool:
    """Create a tasks row via REST when missing so execution_receipts FK succeeds."""
    try:
        from app.core.supabase_rest import rest_insert, rest_select, supabase_rest_configured

        if not supabase_rest_configured() or not task_id:
            return False
        existing = rest_select(
            "tasks",
            {"id": f"eq.{task_id}", "select": "id", "limit": "1"},
        )
        if existing:
            return True
        rest_insert(
            "tasks",
            {
                "id": task_id,
                "process_id": process_id,
                "title": f"Execution task {task_id[:8]}",
                "status": "IN_PROGRESS",
                "task_type": "EXECUTE_TASK",
            },
        )
        return True
    except Exception as exc:
        logger.warning(f"ensure_task REST failed for {task_id!r}: {exc}")
        return False


def _persist_receipt_rest(
    *,
    receipt_id: uuid.UUID,
    process_id: str,
    task_id: str,
    agent_id: str,
    tool_name: str,
    action: str,
    attempt_number: int,
    idempotency_key: str,
    started_at: datetime,
    completed_at: datetime,
    status: str,
    result: Dict[str, Any],
    error_type: Optional[str],
    error_message: Optional[str],
    latency_ms: int,
) -> None:
    try:
        from app.core.supabase_rest import rest_insert, supabase_rest_configured

        if not supabase_rest_configured():
            return
        if not _ensure_task_rest(process_id, task_id):
            return
        rest_insert(
            "execution_receipts",
            {
                "id": str(receipt_id),
                "process_id": process_id,
                "task_id": task_id,
                "agent_id": agent_id or "agent_2",
                "tool_name": tool_name,
                "action": action,
                "attempt_number": attempt_number,
                "idempotency_key": idempotency_key,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "status": status,
                "result": result or {},
                "error_type": error_type,
                "error_message": error_message,
                "latency_ms": latency_ms,
            },
        )
        event_type = "TASK_COMPLETED" if status == "SUCCESS" else f"TOOL_{status}"
        event_row: Dict[str, Any] = {
            "process_id": process_id,
            "event_type": event_type,
            "actor": agent_id or "agent_2",
            "agent": "agent_2",
            "previous_state": "RUNNING",
            "new_state": status,
            "metadata_json": {
                "tool_name": tool_name,
                "attempt_number": attempt_number,
                "idempotency_key": idempotency_key,
                "latency_ms": latency_ms,
                "receipt_id": str(receipt_id),
            },
        }
        if task_id:
            event_row["task_id"] = task_id
        try:
            rest_insert("workflow_events", event_row)
        except Exception:
            event_row.pop("task_id", None)
            rest_insert("workflow_events", event_row)
    except Exception as exc:
        logger.warning(f"REST persist execution receipt failed: {exc}")


async def create_receipt(
    session: Optional[AsyncSession],
    process_id: str,
    task_id: str,
    agent_id: str,
    tool_name: str,
    action: str,
    attempt_number: int,
    idempotency_key: str,
    started_at: datetime,
    completed_at: Optional[datetime],
    status: str,
    result: Optional[Dict[str, Any]] = None,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    latency_ms: int = 0,
) -> ExecutionReceipt:
    """
    Construct and persist an ExecutionReceipt record and a matching WorkflowEvent.

    :return: Constructed ExecutionReceipt ORM instance
    """
    proc_uuid = parse_uuid(process_id)
    task_uuid = parse_uuid(task_id)
    receipt_id = uuid.uuid4()
    completed = completed_at or datetime.now(timezone.utc)
    result_payload = result or {}

    if session is not None:
        await ensure_process_instance(session, process_id)
        await ensure_task(session, process_id, task_id)

    receipt_row = ExecutionReceipt(
        id=receipt_id,
        process_id=proc_uuid,
        task_id=task_uuid,
        agent_id=agent_id or "agent_2",
        tool_name=tool_name,
        action=action,
        attempt_number=attempt_number,
        idempotency_key=idempotency_key,
        started_at=started_at,
        completed_at=completed,
        status=status,
        result=result_payload,
        error_type=error_type or None,
        error_message=error_message or None,
        latency_ms=latency_ms,
        created_at=started_at,
        updated_at=completed,
    )

    event_type = "TASK_COMPLETED" if status == "SUCCESS" else f"TOOL_{status}"
    workflow_event_row = WorkflowEvent(
        id=uuid.uuid4(),
        process_id=proc_uuid,
        task_id=task_uuid,
        event_type=event_type,
        actor=agent_id or "agent_2",
        agent="agent_2",
        timestamp=completed,
        previous_state="RUNNING",
        new_state=status,
        metadata_json={
            "tool_name": tool_name,
            "attempt_number": attempt_number,
            "idempotency_key": idempotency_key,
            "latency_ms": latency_ms,
        },
    )

    persisted = False
    if session is not None:
        try:
            session.add(receipt_row)
            session.add(workflow_event_row)
            if status == "SUCCESS" and tool_name in {"send_email", "send_reminder"}:
                session.add(
                    EmailEvent(
                        id=uuid.uuid4(),
                        execution_receipt_id=receipt_id,
                        recipient_email=(result_payload or {}).get("recipient") or "",
                        recipient_role="manager",
                        subject=(result_payload or {}).get("subject") or tool_name,
                        template_name="",
                        status=(result_payload or {}).get("status") or "SENT",
                        sent_at=completed,
                    )
                )
            await session.commit()
            persisted = True
        except Exception as exc:
            logger.warning(f"Failed to persist execution receipt: {exc}")
            try:
                await session.rollback()
            except Exception:
                pass

    if not persisted:
        _persist_receipt_rest(
            receipt_id=receipt_id,
            process_id=process_id,
            task_id=task_id,
            agent_id=agent_id,
            tool_name=tool_name,
            action=action,
            attempt_number=attempt_number,
            idempotency_key=idempotency_key,
            started_at=started_at,
            completed_at=completed,
            status=status,
            result=result_payload,
            error_type=error_type,
            error_message=error_message,
            latency_ms=latency_ms,
        )

    # Always mirror a compact last_execution onto the process so invoice UI
    # and process detail can see the tool outcome without SQLAlchemy.
    await merge_process_metadata(
        session,
        process_id,
        {
            "last_execution": {
                "receipt_id": str(receipt_id),
                "tool_name": tool_name,
                "status": status,
                "result": result_payload,
                "error_message": error_message,
                "latency_ms": latency_ms,
                "completed_at": completed.isoformat(),
            }
        },
    )

    return receipt_row
