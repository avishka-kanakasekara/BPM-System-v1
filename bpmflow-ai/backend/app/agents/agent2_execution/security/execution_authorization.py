"""
Agent 2 — Execution authorization (Agent 4 governance).

Authorization model (single source of truth):

1. **Inter-agent path** (Agent 4 → Agent 2 adapter):
   - `message.status` MUST be `"AUTHORIZED"`.
   - Enforced in `message_handler.process_inbound_message` and `Agent2Adapter`.

2. **Mutating / external tools** (UI or API):
   - Process `current_stage` MUST be `WORKFLOW_EXECUTION`.
   - Agent 4 is the sole writer of `current_stage`; reaching WORKFLOW_EXECUTION
     means risk review and human approval completed.

3. **Read-only analytics tools**:
   - Valid `process_id` required; no stage gate.

4. **Retries**:
   - Original receipt must exist and be eligible (FAILED, not SUCCESS).
   - Process must still be at WORKFLOW_EXECUTION for mutating tools.
   - Bounded retry count per logical operation.

Never trust frontend status, stage, or role flags — always re-validate server-side.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.agent.planner_fallback import (
    FULL_TASK_SUITE_TOOL,
    is_full_task_suite,
)
from app.agents.agent2_execution.database.ids import parse_uuid
from app.agents.agent2_execution.database.models import ExecutionReceipt
from app.agents.agent2_execution.tools.metadata import READ_ONLY_TOOLS
from app.agents.agent4_orchestrator.constants import WorkflowStage
from app.agents.agent4_orchestrator.exceptions import ProcessNotFoundError
from app.agents.agent4_orchestrator.repository import ProcessRepository

MAX_USER_RETRIES = 3


@dataclass
class AuthorizationResult:
    authorized: bool
    error_code: str = ""
    message: str = ""
    stage: str = ""


def _stage_value(process) -> str:
    return getattr(process.current_stage, "value", str(process.current_stage or "")).upper()


async def authorize_tool_execution(
    repository: ProcessRepository,
    process_id: str,
    tool_name: str,
) -> AuthorizationResult:
    """Validate Agent 4 execution gate for a tool invocation."""
    tool = tool_name.strip().lower()
    if is_full_task_suite(tool):
        tool = FULL_TASK_SUITE_TOOL
    if tool in READ_ONLY_TOOLS:
        try:
            await repository.get_process(uuid.UUID(process_id))
            return AuthorizationResult(authorized=True, stage="READ_ONLY")
        except (ProcessNotFoundError, ValueError):
            return AuthorizationResult(
                authorized=False,
                error_code="PROCESS_NOT_FOUND",
                message="Process not found",
            )

    try:
        process = await repository.get_process(uuid.UUID(process_id))
    except (ProcessNotFoundError, ValueError):
        return AuthorizationResult(
            authorized=False,
            error_code="PROCESS_NOT_FOUND",
            message="Process not found",
        )

    stage = _stage_value(process)
    if stage != WorkflowStage.WORKFLOW_EXECUTION.value:
        return AuthorizationResult(
            authorized=False,
            error_code="NOT_AUTHORIZED",
            message=(
                f"Tool {tool!r} requires Agent 4 authorization. "
                f"Process must be at WORKFLOW_EXECUTION (current: {stage})."
            ),
            stage=stage,
        )
    return AuthorizationResult(authorized=True, stage=stage)


async def authorize_retry(
    repository: ProcessRepository,
    session: AsyncSession | None,
    *,
    receipt_id: str,
    process_id: str,
    task_id: str,
    tool_name: str,
) -> AuthorizationResult:
    """Validate retry eligibility before re-execution."""
    base = await authorize_tool_execution(repository, process_id, tool_name)
    if not base.authorized:
        return base

    if session is None:
        return AuthorizationResult(
            authorized=False,
            error_code="DATABASE_UNAVAILABLE",
            message="Retry requires database persistence",
        )

    try:
        rec_uuid = parse_uuid(receipt_id)
    except ValueError:
        return AuthorizationResult(
            authorized=False,
            error_code="RECEIPT_NOT_FOUND",
            message="Invalid receipt id",
        )

    res = await session.execute(
        select(ExecutionReceipt).where(ExecutionReceipt.id == rec_uuid)
    )
    original = res.scalar_one_or_none()
    if original is None:
        return AuthorizationResult(
            authorized=False,
            error_code="RECEIPT_NOT_FOUND",
            message="Original execution receipt not found",
        )

    if str(original.process_id) != process_id or str(original.task_id) != task_id:
        return AuthorizationResult(
            authorized=False,
            error_code="RECEIPT_MISMATCH",
            message="Receipt does not match the supplied process/task",
        )

    if original.tool_name.strip().lower() != tool_name.strip().lower():
        return AuthorizationResult(
            authorized=False,
            error_code="TOOL_MISMATCH",
            message="Tool name does not match original receipt",
        )

    if original.status == "SUCCESS":
        return AuthorizationResult(
            authorized=False,
            error_code="ALREADY_SUCCEEDED",
            message="Cannot retry a successful execution; idempotency applies",
        )

    if original.status not in {"FAILED", "BLOCKED", "RETRYING"}:
        return AuthorizationResult(
            authorized=False,
            error_code="NOT_RETRYABLE",
            message=f"Receipt status {original.status!r} is not eligible for retry",
        )

    base_key = f"{process_id}-{task_id}-{tool_name.strip().lower()}"
    retry_count_res = await session.execute(
        select(func.count())
        .select_from(ExecutionReceipt)
        .where(
            ExecutionReceipt.idempotency_key.like(f"{base_key}-retry-%"),
        )
    )
    retry_count = int(retry_count_res.scalar() or 0)
    if retry_count >= MAX_USER_RETRIES:
        return AuthorizationResult(
            authorized=False,
            error_code="RETRY_LIMIT_EXCEEDED",
            message=f"Maximum retry limit ({MAX_USER_RETRIES}) reached for this operation",
        )

    return AuthorizationResult(authorized=True, stage=base.stage)
