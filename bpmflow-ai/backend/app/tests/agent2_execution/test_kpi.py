"""
Agent 2 — KPI Engine & Process Mining Unit Tests

Tests cycle time, waiting time, PM4Py log generation, and KPI metrics calculations
against known hand-constructed event logs.
"""

from datetime import datetime, timedelta, timezone
import pandas as pd
import pytest

from app.agents.agent2_execution.analytics import cycle_time, event_analyzer, kpi_engine, waiting_time


# ---------------------------------------------------------------------------
# 1. Cycle Time Analytics Unit Tests
# ---------------------------------------------------------------------------

def test_cycle_time_calculation():
    # Hand-constructed log for 2 cases
    t0 = datetime(2026, 8, 15, 10, 0, 0, tzinfo=timezone.utc)
    data = [
        {"case:concept:name": "case-1", "concept:name": "Request Validation", "time:timestamp": t0},
        {"case:concept:name": "case-1", "concept:name": "Manager Approval", "time:timestamp": t0 + timedelta(hours=2, minutes=30)},
        {"case:concept:name": "case-2", "concept:name": "Request Validation", "time:timestamp": t0},
        {"case:concept:name": "case-2", "concept:name": "PO Creation", "time:timestamp": t0 + timedelta(hours=5)},
    ]
    df = pd.DataFrame(data)

    case_times = cycle_time.calculate_case_cycle_times(df)
    assert case_times["case-1"] == 2.5
    assert case_times["case-2"] == 5.0

    avg_cycle = cycle_time.calculate_average_cycle_time(df)
    assert avg_cycle == 3.75  # (2.5 + 5.0) / 2 = 3.75h


# ---------------------------------------------------------------------------
# 2. Waiting Time & Bottleneck Mining Unit Tests
# ---------------------------------------------------------------------------

def test_waiting_time_calculation():
    t0 = datetime(2026, 8, 15, 10, 0, 0, tzinfo=timezone.utc)
    # Case 1: Request Validation at t0, Manager Approval 18.0h later
    data = [
        {"case:concept:name": "case-1", "concept:name": "Request Validation", "time:timestamp": t0},
        {"case:concept:name": "case-1", "concept:name": "Manager Approval", "time:timestamp": t0 + timedelta(hours=18)},
        {"case:concept:name": "case-1", "concept:name": "PO Creation", "time:timestamp": t0 + timedelta(hours=18, minutes=15)},
    ]
    df = pd.DataFrame(data)

    activity_waits = waiting_time.calculate_activity_waiting_times(df)
    assert activity_waits["Manager Approval"] == 18.0
    assert activity_waits["PO Creation"] == 0.25  # 15 minutes = 0.25h

    avg_wait = waiting_time.calculate_average_waiting_time(df)
    assert avg_wait == round((18.0 + 0.25) / 2.0, 4)  # 9.125h


# ---------------------------------------------------------------------------
# 3. PM4Py Event Log Transformation Test
# ---------------------------------------------------------------------------

def test_build_pm4py_event_log():
    raw_events = [
        {
            "process_id": "proc-100",
            "task_id": "task-200",
            "event_type": "TASK_COMPLETED",
            "actor": "agent_2",
            "timestamp": "2026-08-15T10:00:00Z",
            "metadata_json": {"tool_name": "create_po_draft"},
        }
    ]
    df = event_analyzer.build_pm4py_event_log(raw_events)
    assert not df.empty
    assert "case:concept:name" in df.columns
    assert "concept:name" in df.columns
    assert "time:timestamp" in df.columns
    assert df.iloc[0]["case:concept:name"] == "proc-100"
    assert df.iloc[0]["concept:name"] == "create_po_draft"
