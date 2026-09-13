"""
Agent 2 — Idempotency Subsystem Tests

Enforces Non-Negotiable Rule #3:
Same key called twice only executes once — second call short-circuits and returns existing SUCCESS receipt.
"""

import uuid

import pytest

from app.agents.agent2_execution.execution.execution_engine import execute_with_recovery
from app.agents.agent2_execution.execution.idempotency import (
    clear_memory_receipts,
    generate_idempotency_key,
)
from app.agents.agent2_execution.llm.gemini_client import GeminiClient
from app.agents.agent2_execution.security.tool_guard import ExecutionGuardContext


def test_idempotency_key_generation():
    proc_id = "proc-1001"
    task_id = "task-2002"
    action = "create_po_draft"
    key = generate_idempotency_key(proc_id, task_id, action)
    assert key == "proc-1001-task-2002-create_po_draft"


@pytest.mark.asyncio
async def test_idempotency_short_circuit():
    clear_memory_receipts()
    proc_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    tool_name = "create_po_draft"
    params = {
        "vendor_id": "vendor-100",
        "amount": 1500.00,
        "process_id": proc_id,
        "task_id": task_id,
    }
    gemini_client = GeminiClient(is_offline=True)
    guard = ExecutionGuardContext(
        message_status="AUTHORIZED",
        process_stage="WORKFLOW_EXECUTION",
        process_id=proc_id,
    )

    receipt1 = await execute_with_recovery(
        process_id=proc_id,
        task_id=task_id,
        tool_name=tool_name,
        parameters=params,
        session=None,
        gemini_client=gemini_client,
        guard_context=guard,
    )
    assert receipt1.status == "SUCCESS"
    assert receipt1.attempt_number == 1
    assert receipt1.idempotency_key == f"{proc_id}-{task_id}-{tool_name}"

    receipt2 = await execute_with_recovery(
        process_id=proc_id,
        task_id=task_id,
        tool_name=tool_name,
        parameters=params,
        session=None,
        gemini_client=gemini_client,
        guard_context=guard,
    )
    assert receipt2.status == "SUCCESS"
    assert receipt2.id == receipt1.id


@pytest.mark.asyncio
async def test_concurrent_idempotency_replays():
    """Adversarial Case 3: Replaying the same idempotency key 5 times concurrently."""
    import asyncio

    clear_memory_receipts()
    proc_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    tool_name = "create_po_draft"
    params = {
        "vendor_id": "vendor-100",
        "amount": 1500.00,
        "process_id": proc_id,
        "task_id": task_id,
    }
    gemini_client = GeminiClient(is_offline=True)
    guard = ExecutionGuardContext(
        message_status="AUTHORIZED",
        process_stage="WORKFLOW_EXECUTION",
        process_id=proc_id,
    )

    tasks = [
        execute_with_recovery(
            process_id=proc_id,
            task_id=task_id,
            tool_name=tool_name,
            parameters=params,
            session=None,
            gemini_client=gemini_client,
            guard_context=guard,
        )
        for _ in range(5)
    ]

    receipts = await asyncio.gather(*tasks)

    assert len(receipts) == 5
    success_ids = {r.id for r in receipts if r.status == "SUCCESS"}
    assert len(success_ids) == 1
    for r in receipts:
        assert r.status == "SUCCESS"
        assert r.idempotency_key == f"{proc_id}-{task_id}-{tool_name}"
