"""
Agent 2 — Event Log Analyzer & PM4Py Data Preparation

Provides event log extraction and transformation helpers, converting workflow_events database rows
and Task stage records into PM4Py-compatible Pandas DataFrames with standard PM4Py log columns:
- case:concept:name -> process_id
- concept:name -> activity (process stage title)
- time:timestamp -> timestamp
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Task, WorkflowEvent

logger = logging.getLogger("agent_2.analytics.event_analyzer")


async def fetch_workflow_events(
    session: Optional[AsyncSession],
    process_id: Optional[str] = None,
    since: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Fetch workflow_events and Task stage records from DB as clean dicts."""
    if session is None:
        return []

    events = []

    # 1. Fetch Task Stage Events from tasks table
    try:
        stmt_t = select(Task).where(Task.completed_at.is_not(None)).order_by(Task.started_at.asc())
        if process_id:
            try:
                import uuid
                stmt_t = stmt_t.where(Task.process_instance_id == uuid.UUID(process_id))
            except ValueError:
                pass
        if since:
            stmt_t = stmt_t.where(Task.created_at >= since)

        res_t = await session.execute(stmt_t)
        tasks = res_t.scalars().all()
        for t in tasks:
            events.append({
                "id": f"task-start-{t.id}",
                "process_id": str(t.process_instance_id),
                "task_id": str(t.id),
                "event_type": "TASK_STARTED",
                "actor": t.assigned_role or "agent_2",
                "timestamp": t.started_at,
                "previous_state": "PENDING",
                "new_state": "IN_PROGRESS",
                "metadata_json": {"activity_name": t.title},
            })
            events.append({
                "id": f"task-complete-{t.id}",
                "process_id": str(t.process_instance_id),
                "task_id": str(t.id),
                "event_type": "TASK_COMPLETED",
                "actor": t.assigned_role or "agent_2",
                "timestamp": t.completed_at,
                "previous_state": "IN_PROGRESS",
                "new_state": "COMPLETED",
                "metadata_json": {"activity_name": t.title},
            })
    except Exception as e:
        logger.warning(f"Failed to fetch task stage events: {e}")

    # 2. Fetch WorkflowEvent rows
    stmt_w = select(WorkflowEvent).order_by(WorkflowEvent.timestamp.asc())
    if process_id:
        try:
            import uuid
            stmt_w = stmt_w.where(WorkflowEvent.process_id == uuid.UUID(process_id))
        except ValueError:
            pass
    if since:
        stmt_w = stmt_w.where(WorkflowEvent.timestamp >= since)

    res_w = await session.execute(stmt_w)
    rows = res_w.scalars().all()

    for r in rows:
        events.append({
            "id": str(r.id),
            "process_id": str(r.process_id),
            "task_id": str(r.task_id) if r.task_id else "",
            "event_type": r.event_type,
            "actor": r.actor,
            "timestamp": r.timestamp,
            "previous_state": r.previous_state,
            "new_state": r.new_state,
            "metadata_json": r.metadata_json or {},
        })

    return events


def build_pm4py_event_log(events: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Transform raw workflow event dicts into a PM4Py standard EventLog DataFrame.

    :param events: List of workflow event dicts
    :return: Formatted PM4Py DataFrame
    """
    if not events:
        return pd.DataFrame(
            columns=["case:concept:name", "concept:name", "time:timestamp", "task_id", "actor"]
        )

    records = []
    for ev in events:
        # Exclude exception events (e.g. REWORK) from process stage activity log
        if ev.get("event_type") == "REWORK":
            continue

        meta = ev.get("metadata_json") or {}
        activity_name = meta.get("activity_name") or meta.get("tool_name") or ev["event_type"]

        # Only log events with defined activity names (process stage titles or tool names)
        if activity_name in ["PROCESS_STARTED", "PROCESS_COMPLETED"]:
            continue

        records.append(
            {
                "case:concept:name": str(ev["process_id"]),
                "concept:name": str(activity_name),
                "time:timestamp": pd.to_datetime(ev["timestamp"]),
                "task_id": str(ev["task_id"]),
                "actor": str(ev["actor"]),
                "event_type": str(ev.get("event_type", "")),
                "new_state": str(ev.get("new_state", "")),
            }
        )

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.sort_values(by=["case:concept:name", "time:timestamp"]).reset_index(drop=True)

    return df
