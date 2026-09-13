"""
Agent 2 — Execution Engine Orchestrator

Composes Idempotency Guard, Tool Guard, Executor, Failure Analyzer, Retry Manager,
and Receipt Manager into a unified orchestrator function:

execute_with_recovery(process_id, task_id, tool_name, parameters, session) -> ExecutionReceipt
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.database.models import ExecutionReceipt
from app.agents.agent2_execution.execution import (
    failure_analyzer,
    idempotency,
    receipt_manager,
    retry_manager,
)
from app.agents.agent2_execution.execution.executor import execute_tool
from app.agents.agent2_execution.llm.gemini_client import GeminiClient
from app.agents.agent2_execution.security.tool_guard import ExecutionGuardContext, ToolGuard

logger = logging.getLogger("agent_2.execution.execution_engine")


async def execute_with_recovery(
    process_id: str,
    task_id: str,
    tool_name: str,
    parameters: dict[str, Any],
    session: AsyncSession | None = None,
    actor: str = "agent_2",
    is_idempotent: bool | None = None,
    idempotency_key: str | None = None,
    gemini_client: GeminiClient | None = None,
    guard_context: ExecutionGuardContext | None = None,
) -> ExecutionReceipt:
    """
    Main entry point for tool execution with security gating, idempotency checking,
    failure classification, and intelligent recovery retries.

    :param process_id: Process instance ID
    :param task_id: Task ID
    :param tool_name: Target tool identifier
    :param parameters: Tool parameter arguments dict
    :param session: Active AsyncSession (optional)
    :param actor: Calling actor identifier
    :param is_idempotent: Optional idempotency override boolean
    :param gemini_client: Optional GeminiClient instance
    :return: Persisted ExecutionReceipt ORM record
    """
    idempotency_key = idempotency_key or idempotency.generate_idempotency_key(
        process_id, task_id, tool_name
    )

    # Step 1: Idempotency Check (Rule #3)
    existing_receipt = await idempotency.check_existing_receipt(session, idempotency_key)
    if existing_receipt:
        logger.info(f"IDEMPOTENCY SHORT-CIRCUIT: Existing SUCCESS receipt found for key {idempotency_key!r}")
        return existing_receipt

    # Step 2: Tool Guard Security Check (Rules #1, #2, #4, #6, #7)
    guard = ToolGuard(session=session)
    ctx = guard_context or ExecutionGuardContext(process_id=process_id)
    if not ctx.process_id:
        ctx = ExecutionGuardContext(
            message_status=ctx.message_status,
            process_stage=ctx.process_stage,
            is_retry=ctx.is_retry,
            process_id=process_id,
        )
    guard_result = await guard.check(
        tool_name,
        parameters,
        actor=actor,
        guard_context=ctx,
    )

    if not guard_result.allowed:
        logger.warning(f"TOOL GUARD BLOCKED tool call {tool_name!r}: {guard_result.reason}")
        now = datetime.now(UTC)
        return await receipt_manager.create_receipt(
            session=session,
            process_id=process_id,
            task_id=task_id,
            agent_id=actor,
            tool_name=tool_name,
            action=tool_name,
            attempt_number=1,
            idempotency_key=idempotency_key,
            started_at=now,
            completed_at=now,
            status="BLOCKED",
            error_type=guard_result.error or "BLOCKED_BY_GUARD",
            error_message=guard_result.reason,
            latency_ms=0,
        )

    # Step 3: Execution & Recovery Loop (up to 3 attempts)
    max_attempts = 3
    last_error = ""
    last_diagnosis = None

    for attempt_number in range(1, max_attempts + 1):
        started_at = datetime.now(UTC)

        # ACT: Invoke tool via executor
        success, result_data, latency_ms, error_msg = await execute_tool(
            session, tool_name, parameters
        )
        completed_at = datetime.now(UTC)

        if success:
            logger.info(f"Tool {tool_name!r} executed successfully on attempt {attempt_number}")
            return await receipt_manager.create_receipt(
                session=session,
                process_id=process_id,
                task_id=task_id,
                agent_id=actor,
                tool_name=tool_name,
                action=tool_name,
                attempt_number=attempt_number,
                idempotency_key=idempotency_key,
                started_at=started_at,
                completed_at=completed_at,
                status="SUCCESS",
                result=result_data,
                latency_ms=latency_ms,
            )

        # OBSERVE & DIAGNOSE: Tool call failed
        last_error = error_msg
        diagnosis = await failure_analyzer.analyze_failure(
            error_message=error_msg,
            tool_name=tool_name,
            attempt_number=attempt_number,
            gemini_client=gemini_client,
        )
        last_diagnosis = diagnosis

        # RECOVER: Evaluate retry decision
        recovery = await retry_manager.evaluate_retry(
            action=tool_name,
            attempt_number=attempt_number,
            diagnosis=diagnosis,
            is_idempotent=is_idempotent,
            gemini_client=gemini_client,
        )

        logger.warning(
            f"Attempt {attempt_number} failed for {tool_name!r} ({diagnosis.failure_type}): {recovery.reasoning}"
        )

        if recovery.retry and attempt_number < max_attempts:
            # Sleep backoff delay (capped for tests)
            sleep_sec = min(recovery.delay_seconds, 0.1) if gemini_client and gemini_client.is_offline else min(recovery.delay_seconds, 2)
            if sleep_sec > 0:
                await asyncio.sleep(sleep_sec)
            continue
        else:
            # Retry denied or attempt limit reached -> Write FAILED receipt
            return await receipt_manager.create_receipt(
                session=session,
                process_id=process_id,
                task_id=task_id,
                agent_id=actor,
                tool_name=tool_name,
                action=tool_name,
                attempt_number=attempt_number,
                idempotency_key=idempotency_key,
                started_at=started_at,
                completed_at=completed_at,
                status="FAILED",
                error_type=diagnosis.failure_type,
                error_message=error_msg,
                latency_ms=latency_ms,
            )

    # Fallback default receipt
    now = datetime.now(UTC)
    return await receipt_manager.create_receipt(
        session=session,
        process_id=process_id,
        task_id=task_id,
        agent_id=actor,
        tool_name=tool_name,
        action=tool_name,
        attempt_number=max_attempts,
        idempotency_key=idempotency_key,
        started_at=now,
        completed_at=now,
        status="FAILED",
        error_type=last_diagnosis.failure_type if last_diagnosis else "UNKNOWN",
        error_message=last_error,
        latency_ms=0,
    )
