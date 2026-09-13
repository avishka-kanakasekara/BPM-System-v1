"""
Agent 2 — Idempotency Subsystem

Enforces Non-Negotiable Rule #3:
Builds idempotency key as f"{process_id}-{task_id}-{action}".
Checks execution_receipts for a prior row with that key and status=SUCCESS before anything executes.
If found, short-circuits and returns the existing receipt instead of re-running the tool.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.database.models import ExecutionReceipt

# In-memory SUCCESS receipts for tests when session is unavailable.
_memory_success_receipts: dict[str, ExecutionReceipt] = {}


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


SIDE_EFFECT_TOOLS = frozenset(
    {
        "send_email",
        "send_reminder",
        "request_quotation",
        "create_po_draft",
        "match_invoice",
        "update_procurement_record",
        "schedule_escalation",
    }
)


async def check_existing_receipt(
    session: AsyncSession | None, idempotency_key: str
) -> ExecutionReceipt | None:
    """
    Check if a successful execution receipt already exists for this idempotency key.

    :param session: Active AsyncSession (optional)
    :param idempotency_key: Target idempotency key
    :return: Existing ExecutionReceipt ORM instance if SUCCESS found; None otherwise.
    """
    if not idempotency_key:
        return None

    if session is None:
        return _memory_success_receipts.get(idempotency_key)

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


def register_success_receipt(receipt: ExecutionReceipt) -> None:
    """Register a SUCCESS receipt in the in-memory idempotency store (tests)."""
    if receipt.status == "SUCCESS" and receipt.idempotency_key:
        _memory_success_receipts[receipt.idempotency_key] = receipt


def clear_memory_receipts() -> None:
    """Clear in-memory idempotency store (test isolation)."""
    _memory_success_receipts.clear()
