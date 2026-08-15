"""
Agent 2 — Receipt & Workflow Event Manager

Writes execution_receipts records and matching workflow_events records for every tool attempt (success or failure).
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ExecutionReceipt, WorkflowEvent


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
    try:
        proc_uuid = uuid.UUID(process_id) if process_id else uuid.uuid4()
    except (ValueError, TypeError):
        proc_uuid = uuid.uuid4()

    try:
        task_uuid = uuid.UUID(task_id) if task_id else uuid.uuid4()
    except (ValueError, TypeError):
        task_uuid = uuid.uuid4()
    receipt_id = uuid.uuid4()

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
        completed_at=completed_at or datetime.now(timezone.utc),
        status=status,
        result=result or {},
        error_type=error_type or None,
        error_message=error_message or None,
        latency_ms=latency_ms,
        created_at=started_at,
        updated_at=completed_at or datetime.now(timezone.utc),
    )

    event_type = "TASK_COMPLETED" if status == "SUCCESS" else f"TOOL_{status}"
    workflow_event_row = WorkflowEvent(
        id=uuid.uuid4(),
        process_id=proc_uuid,
        task_id=task_uuid,
        event_type=event_type,
        actor=agent_id or "agent_2",
        agent="agent_2",
        timestamp=completed_at or datetime.now(timezone.utc),
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
        session.add(receipt_row)
        session.add(workflow_event_row)
        await session.commit()

    return receipt_row
