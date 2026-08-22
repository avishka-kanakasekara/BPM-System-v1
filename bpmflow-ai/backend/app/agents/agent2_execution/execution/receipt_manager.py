"""
Agent 2 — Receipt & Workflow Event Manager

Writes execution_receipts records and matching workflow_events records for every tool attempt (success or failure).
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.database.ids import parse_uuid
from app.agents.agent2_execution.database.models import EmailEvent, ExecutionReceipt, WorkflowEvent
from app.agents.agent2_execution.database.persistence import ensure_process_instance, ensure_task

logger = logging.getLogger("agent_2.execution.receipt_manager")


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
        result=result or {},
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

    if session is not None:
        try:
            session.add(receipt_row)
            session.add(workflow_event_row)
            if status == "SUCCESS" and tool_name in {"send_email", "send_reminder"}:
                session.add(
                    EmailEvent(
                        id=uuid.uuid4(),
                        execution_receipt_id=receipt_id,
                        recipient_email=(result or {}).get("recipient") or "",
                        recipient_role="manager",
                        subject=(result or {}).get("subject") or tool_name,
                        template_name="",
                        status=(result or {}).get("status") or "SENT",
                        sent_at=completed,
                    )
                )
            await session.commit()
        except Exception as exc:
            logger.warning(f"Failed to persist execution receipt: {exc}")
            try:
                await session.rollback()
            except Exception:
                pass

    return receipt_row
