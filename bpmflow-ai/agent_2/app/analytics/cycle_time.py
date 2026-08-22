"""
Agent 2 — Cycle Time Process Mining Subsystem

Computes per-case and average cycle times (total elapsed time from process creation to completion)
using PM4Py process analytics and Pandas log aggregations.
"""

from typing import Dict
import pandas as pd


def calculate_case_cycle_times(df: pd.DataFrame) -> Dict[str, float]:
    """
    Compute total cycle time in hours for each process instance (case_id).

    :param df: PM4Py-formatted DataFrame with case:concept:name and time:timestamp columns
    :return: Dict mapping process_id -> cycle_time_hours
    """
    if df.empty:
        return {}

    grouped = df.groupby("case:concept:name")["time:timestamp"]
    start_times = grouped.min()
    end_times = grouped.max()

    durations = (end_times - start_times).dt.total_seconds() / 3600.0
    return {str(case_id): round(float(dur), 4) for case_id, dur in durations.items()}


def calculate_average_cycle_time(df: pd.DataFrame) -> float:
    """
    Compute overall average cycle time in hours across all process instances.

    :param df: PM4Py-formatted DataFrame
    :return: Mean cycle time in hours
    """
    case_times = calculate_case_cycle_times(df)
    if not case_times:
        return 0.0

    mean_val = sum(case_times.values()) / float(len(case_times))
    return round(mean_val, 4)
