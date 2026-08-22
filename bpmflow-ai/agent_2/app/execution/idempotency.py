"""
Agent 2 — Idempotency Subsystem

Enforces Non-Negotiable Rule #3:
Builds idempotency key as f"{process_id}-{task_id}-{action}".
Checks execution_receipts for a prior row with that key and status=SUCCESS before anything executes.
If found, short-circuits and returns the existing receipt instead of re-running the tool.
"""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ExecutionReceipt


def generate_idempotency_key(process_id: str, task_id: str, action: str) -> str:
    """
    Construct a deterministic idempotency key.
    
    :param process_id: Process instance UUID string
    :param task_id: Task UUID string
    :param action: Action or tool name string
    :return: Formatted idempotency key string
    """
    p_clean = str(process_id).strip()
    t_clean = str(task_id).strip()
    a_clean = str(action).strip().lower()
    return f"{p_clean}-{t_clean}-{a_clean}"


async def check_existing_receipt(
    session: Optional[AsyncSession], idempotency_key: str
) -> Optional[ExecutionReceipt]:
    """
    Check if a successful execution receipt already exists for this idempotency key.

    :param session: Active AsyncSession (optional)
    :param idempotency_key: Target idempotency key
    :return: Existing ExecutionReceipt ORM instance if SUCCESS found; None otherwise.
    """
    if session is None or not idempotency_key:
        return None

    stmt = (
        select(ExecutionReceipt)
        .where(
            ExecutionReceipt.idempotency_key == idempotency_key,
            ExecutionReceipt.status == "SUCCESS",
        )
        .order_by(ExecutionReceipt.created_at.desc())
        .limit(1)
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()
