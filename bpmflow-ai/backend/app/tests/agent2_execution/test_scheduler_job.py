"""Scheduler due-job execution test (no Redis required)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_scheduler_executes_due_job():
    from app.agents.agent2_execution.scheduler import service as scheduler_service

    job = {
        "id": str(uuid4()),
        "job_type": "REMINDER",
        "process_id": str(uuid4()),
        "task_id": str(uuid4()),
        "payload_json": {
            "recipient": "frank.miller@acmeglobal.com",
            "subject": "Due reminder",
            "message": "Task is due",
            "process_id": str(uuid4()),
            "task_id": str(uuid4()),
        },
        "scheduled_for": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
        "status": "CLAIMED",
        "attempts": 1,
        "max_attempts": 3,
    }

    with patch.object(scheduler_service, "_fetch_due_jobs", AsyncMock(return_value=[job])), patch.object(
        scheduler_service,
        "_execute_job",
        AsyncMock(),
    ) as mock_execute, patch.object(scheduler_service, "_update_job_status", AsyncMock()):
        await scheduler_service._poll_once()
        mock_execute.assert_awaited_once()
        assert mock_execute.await_args.args[1]["id"] == job["id"]
