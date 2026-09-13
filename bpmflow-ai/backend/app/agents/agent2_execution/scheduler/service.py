"""
Agent 2 — Background scheduler for reminders and escalations.

Polls scheduled_jobs and executes due work without requiring the browser.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.communication.schemas import EmailRequest
from app.agents.agent2_execution.database.ids import parse_uuid
from app.agents.agent2_execution.database.persistence import record_workflow_event
from app.agents.agent2_execution.tools.email_service import EmailService

logger = logging.getLogger("agent_2.scheduler")

_scheduler_task: asyncio.Task | None = None
_POLL_SECONDS = 30
_WORKER_ID = f"{socket.gethostname()}-{os.getpid()}"
_SUCCESS_EMAIL_STATUSES = frozenset({"ACCEPTED_BY_PROVIDER", "DRY_RUN", "SENT"})


async def enqueue_scheduled_job(
    session: AsyncSession | None,
    *,
    job_type: str,
    process_id: str,
    task_id: str,
    scheduled_for: datetime,
    payload: dict[str, Any],
    idempotency_key: str,
) -> str:
    """Persist a scheduled job row. Returns job id string."""
    job_id = uuid.uuid4()
    row = {
        "id": str(job_id),
        "job_type": job_type,
        "process_id": process_id or None,
        "task_id": task_id or None,
        "payload_json": payload,
        "scheduled_for": scheduled_for.isoformat(),
        "status": "PENDING",
        "idempotency_key": idempotency_key,
    }

    if session is not None:
        try:
            from app.agents.agent2_execution.database.models import ScheduledJob

            session.add(
                ScheduledJob(
                    id=job_id,
                    job_type=job_type,
                    process_id=parse_uuid(process_id) if process_id else None,
                    task_id=parse_uuid(task_id) if task_id else None,
                    payload_json=payload,
                    scheduled_for=scheduled_for,
                    status="PENDING",
                    idempotency_key=idempotency_key,
                )
            )
            await session.commit()
            return str(job_id)
        except Exception as exc:
            logger.warning(f"SQL enqueue scheduled job failed: {exc}")
            try:
                await session.rollback()
            except Exception:
                pass

    try:
        from app.core.supabase_rest import rest_insert, supabase_rest_configured

        if supabase_rest_configured():
            rest_insert("scheduled_jobs", row)
            return str(job_id)
    except Exception as exc:
        logger.warning(f"REST enqueue scheduled job failed: {exc}")

    return str(job_id)


async def _execute_job(session: AsyncSession | None, job: dict[str, Any]) -> None:
    job_type = job.get("job_type") or ""
    payload = job.get("payload_json") or {}
    process_id = str(job.get("process_id") or payload.get("process_id") or "")
    task_id = str(job.get("task_id") or payload.get("task_id") or "")

    if job_type in {"REMINDER", "send_reminder"}:
        service = EmailService(session=session)
        recipient = payload.get("recipient") or ""
        message = payload.get("message") or "Scheduled reminder from BPMFlow Agent 2"
        subject = payload.get("subject") or f"Reminder: Task {task_id}"
        result = await service.send_email(
            EmailRequest(
                recipient=recipient,
                subject=subject,
                body=message,
                process_id=process_id,
                task_id=task_id,
                recipient_role=payload.get("recipient_role") or "manager",
                template_name="reminder.html",
            )
        )
        await record_workflow_event(
            session,
            process_id or task_id,
            "REMINDER_EXECUTED",
            task_id=task_id,
            metadata={"status": result.status, "message_id": result.message_id},
            new_state=result.status,
        )
        job_result = {"status": result.status, "message_id": result.message_id}
    elif job_type in {"ESCALATION", "schedule_escalation"}:
        service = EmailService(session=session)
        role = payload.get("escalation_role") or "manager"
        recipient = payload.get("recipient") or ""
        if recipient:
            subject = f"Escalation: Task {task_id} requires {role} attention"
            body = payload.get("message") or f"Task {task_id} has exceeded SLA and requires escalation to {role}."
            result = await service.send_email(
                EmailRequest(
                    recipient=recipient,
                    subject=subject,
                    body=body,
                    process_id=process_id,
                    task_id=task_id,
                    recipient_role=role,
                    template_name="escalation.html",
                )
            )
            job_result = {"status": result.status, "message_id": result.message_id}
        else:
            job_result = {"status": "SKIPPED", "reason": "no recipient configured"}
        await record_workflow_event(
            session,
            process_id or task_id,
            "ESCALATION_EXECUTED",
            task_id=task_id,
            metadata=job_result,
            new_state=job_result.get("status") or "EXECUTED",
        )
    else:
        job_result = {"status": "SKIPPED", "reason": f"unknown job_type {job_type!r}"}

    job_id = str(job.get("id") or "")
    now = datetime.now(UTC)
    ok = job_result.get("status") in _SUCCESS_EMAIL_STATUSES or job_result.get("status") == "SKIPPED"
    patch = {
        "status": "SUCCESS" if ok else "FAILED",
        "executed_at": now.isoformat(),
        "result_json": job_result,
        "updated_at": now.isoformat(),
        "claimed_at": None,
        "claimed_by": None,
    }
    await _update_job_status(session, job_id, patch)


async def _update_job_status(
    session: AsyncSession | None, job_id: str, patch: dict[str, Any]
) -> None:
    if session is not None:
        try:
            from app.agents.agent2_execution.database.models import ScheduledJob

            res = await session.execute(
                select(ScheduledJob).where(ScheduledJob.id == parse_uuid(job_id))
            )
            row = res.scalar_one_or_none()
            if row:
                row.status = patch.get("status") or row.status
                row.executed_at = datetime.fromisoformat(patch["executed_at"]) if patch.get("executed_at") else row.executed_at
                row.result_json = patch.get("result_json") or row.result_json
                row.updated_at = datetime.now(UTC)
                await session.commit()
                return
        except Exception as exc:
            logger.warning(f"SQL update scheduled job failed: {exc}")
            try:
                await session.rollback()
            except Exception:
                pass

    try:
        from app.core.supabase_rest import rest_update, supabase_rest_configured

        if supabase_rest_configured() and job_id:
            rest_update("scheduled_jobs", {"id": f"eq.{job_id}"}, patch)
    except Exception as exc:
        logger.warning(f"REST update scheduled job failed: {exc}")


async def _claim_jobs_sql(session: AsyncSession, limit: int = 10) -> list[dict[str, Any]]:
    """Atomically claim due jobs so duplicate workers cannot execute twice."""
    from app.agents.agent2_execution.database.models import ScheduledJob

    now = datetime.now(UTC)
    claimed: list[dict[str, Any]] = []
    res = await session.execute(
        select(ScheduledJob)
        .where(
            ScheduledJob.status == "PENDING",
            ScheduledJob.scheduled_for <= now,
        )
        .order_by(ScheduledJob.scheduled_for.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    rows = res.scalars().all()
    for row in rows:
        row.status = "CLAIMED"
        row.claimed_at = now
        row.claimed_by = _WORKER_ID
        row.attempts = (row.attempts or 0) + 1
        claimed.append(
            {
                "id": str(row.id),
                "job_type": row.job_type,
                "process_id": str(row.process_id) if row.process_id else "",
                "task_id": str(row.task_id) if row.task_id else "",
                "payload_json": row.payload_json or {},
                "scheduled_for": row.scheduled_for.isoformat() if row.scheduled_for else "",
                "status": row.status,
                "idempotency_key": row.idempotency_key,
                "attempts": row.attempts,
                "max_attempts": row.max_attempts,
            }
        )
    if claimed:
        await session.commit()
    return claimed


async def _fetch_due_jobs(session: AsyncSession | None) -> list[dict[str, Any]]:
    if session is not None:
        try:
            return await _claim_jobs_sql(session)
        except Exception as exc:
            logger.debug(f"SQL claim jobs skipped: {exc}")
            try:
                await session.rollback()
            except Exception:
                pass

    now_iso = datetime.now(UTC).isoformat()
    try:
        from app.core.supabase_rest import rest_select, rest_update, supabase_rest_configured

        if supabase_rest_configured():
            due = rest_select(
                "scheduled_jobs",
                {
                    "status": "eq.PENDING",
                    "scheduled_for": f"lte.{now_iso}",
                    "order": "scheduled_for.asc",
                    "limit": "10",
                    "select": "id,job_type,process_id,task_id,payload_json,scheduled_for,status,idempotency_key,attempts,max_attempts",
                },
            )
            claimed = []
            for job in due:
                job_id = str(job.get("id") or "")
                if not job_id:
                    continue
                try:
                    rest_update(
                        "scheduled_jobs",
                        {"id": f"eq.{job_id}", "status": "eq.PENDING"},
                        {
                            "status": "CLAIMED",
                            "claimed_at": now_iso,
                            "claimed_by": _WORKER_ID,
                            "attempts": int(job.get("attempts") or 0) + 1,
                        },
                    )
                    job["status"] = "CLAIMED"
                    claimed.append(job)
                except Exception:
                    continue
            return claimed
    except Exception as exc:
        logger.debug(f"REST claim jobs skipped: {exc}")
    return []


async def _poll_once() -> None:
    session = None
    try:
        from app.core.database import get_session_factory

        factory = get_session_factory()
        session = factory()
    except Exception:
        session = None

    try:
        jobs = await _fetch_due_jobs(session)
        for job in jobs:
            job_id = str(job.get("id") or "")
            logger.info(
                "scheduler_executing_job",
                extra={"job_id": job_id, "job_type": job.get("job_type")},
            )
            try:
                await _execute_job(session, job)
            except Exception as exc:
                logger.exception("scheduler_job_failed", extra={"job_id": job_id})
                attempts = int(job.get("attempts") or 1)
                max_attempts = int(job.get("max_attempts") or 3)
                retry = attempts < max_attempts
                patch: dict[str, Any] = {
                    "status": "PENDING" if retry else "FAILED",
                    "last_error": str(exc),
                    "updated_at": datetime.now(UTC).isoformat(),
                    "claimed_at": None,
                    "claimed_by": None,
                }
                if retry:
                    patch["next_attempt_at"] = (
                        datetime.now(UTC) + timedelta(minutes=min(30, 2**attempts))
                    ).isoformat()
                else:
                    patch["executed_at"] = datetime.now(UTC).isoformat()
                await _update_job_status(session, job_id, patch)
    finally:
        if session is not None:
            try:
                await session.close()
            except Exception:
                pass


async def _scheduler_loop() -> None:
    while True:
        try:
            await _poll_once()
        except Exception:
            logger.exception("scheduler_poll_error")
        await asyncio.sleep(_POLL_SECONDS)


def start_scheduler() -> None:
    """Start background scheduler loop (idempotent)."""
    global _scheduler_task
    if _scheduler_task is not None and not _scheduler_task.done():
        return
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    logger.info("agent2_scheduler_started", extra={"poll_seconds": _POLL_SECONDS})


async def release_scheduler_leases() -> None:
    """Return CLAIMED jobs owned by this worker to PENDING on shutdown."""
    now_iso = datetime.now(UTC).isoformat()
    try:
        from app.core.supabase_rest import rest_select, rest_update, supabase_rest_configured

        if supabase_rest_configured():
            claimed = rest_select(
                "scheduled_jobs",
                {
                    "status": "eq.CLAIMED",
                    "claimed_by": f"eq.{_WORKER_ID}",
                    "select": "id",
                    "limit": "100",
                },
            )
            for job in claimed:
                job_id = str(job.get("id") or "")
                if not job_id:
                    continue
                rest_update(
                    "scheduled_jobs",
                    {"id": f"eq.{job_id}", "status": "eq.CLAIMED"},
                    {
                        "status": "PENDING",
                        "claimed_at": None,
                        "claimed_by": None,
                        "updated_at": now_iso,
                    },
                )
            logger.info(
                "scheduler_leases_released",
                extra={"worker_id": _WORKER_ID, "count": len(claimed)},
            )
    except Exception:
        logger.warning("scheduler_lease_release_failed", exc_info=True)


async def stop_scheduler(*, release_leases: bool = False) -> None:
    """Cancel background scheduler loop; optionally release claimed job leases."""
    global _scheduler_task
    if release_leases:
        await release_scheduler_leases()
    if _scheduler_task is None:
        return
    _scheduler_task.cancel()
    try:
        await _scheduler_task
    except asyncio.CancelledError:
        pass
    _scheduler_task = None
    logger.info("agent2_scheduler_stopped")
