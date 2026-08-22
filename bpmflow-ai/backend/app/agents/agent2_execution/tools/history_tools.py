"""
Agent 2 — History Retrieval Tools (Real DB Queries)

Provides get_process_history and get_task_history querying Agent 2's own DB tables.
"""

import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.database.models import ExecutionAttempt, ExecutionReceipt, Task, ToolCall, WorkflowEvent
from app.agents.agent2_execution.tools.schemas import (
    GetProcessHistoryInput,
    GetProcessHistoryOutput,
    GetTaskHistoryInput,
    GetTaskHistoryOutput,
)


async def get_process_history(
    session: Optional[AsyncSession], input_data: GetProcessHistoryInput
) -> GetProcessHistoryOutput:
    """
    Retrieve workflow event history for a process instance from the database.
    """
    process_id_str = input_data.process_id
    events_out: List[Dict[str, Any]] = []

    if session is not None:
        try:
            proc_uuid = uuid.UUID(process_id_str)
            stmt = (
                select(WorkflowEvent)
                .where(WorkflowEvent.process_id == proc_uuid)
                .order_by(WorkflowEvent.timestamp.asc())
                .limit(input_data.limit)
            )
            res = await session.execute(stmt)
            rows = res.scalars().all()

            for r in rows:
                events_out.append({
                    "id": str(r.id),
                    "event_type": r.event_type,
                    "actor": r.actor,
                    "agent": r.agent,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else "",
                    "previous_state": r.previous_state,
                    "new_state": r.new_state,
                    "metadata": r.metadata_json or {},
                })
        except ValueError:
            pass

    return GetProcessHistoryOutput(
        process_id=process_id_str,
        events=events_out,
        count=len(events_out),
    )


async def get_task_history(
    session: Optional[AsyncSession], input_data: GetTaskHistoryInput
) -> GetTaskHistoryOutput:
    """
    Retrieve execution attempts, tool calls, and receipts for a task from the database.
    """
    task_id_str = input_data.task_id
    attempts_out: List[Dict[str, Any]] = []
    receipts_out: List[Dict[str, Any]] = []

    if session is not None:
        try:
            task_uuid = uuid.UUID(task_id_str)

            # Fetch execution attempts
            stmt_att = (
                select(ExecutionAttempt)
                .where(ExecutionAttempt.task_id == task_uuid)
                .order_by(ExecutionAttempt.attempt_number.asc())
            )
            res_att = await session.execute(stmt_att)
            att_rows = res_att.scalars().all()

            for att in att_rows:
                attempts_out.append({
                    "id": str(att.id),
                    "attempt_number": att.attempt_number,
                    "status": att.status,
                    "started_at": att.started_at.isoformat() if att.started_at else "",
                    "completed_at": att.completed_at.isoformat() if att.completed_at else "",
                    "error_message": att.error_message or "",
                })

            # Fetch receipts
            stmt_rec = (
                select(ExecutionReceipt)
                .where(ExecutionReceipt.task_id == task_uuid)
                .order_by(ExecutionReceipt.created_at.asc())
            )
            res_rec = await session.execute(stmt_rec)
            rec_rows = res_rec.scalars().all()

            for rec in rec_rows:
                receipts_out.append({
                    "id": str(rec.id),
                    "tool_name": rec.tool_name,
                    "action": rec.action,
                    "status": rec.status,
                    "idempotency_key": rec.idempotency_key,
                    "latency_ms": rec.latency_ms or 0,
                    "started_at": rec.started_at.isoformat() if rec.started_at else "",
                })
        except ValueError:
            pass

    return GetTaskHistoryOutput(
        task_id=task_id_str,
        attempts=attempts_out,
        receipts=receipts_out,
    )
