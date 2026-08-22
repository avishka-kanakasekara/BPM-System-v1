"""
Agent 2 — Waiting Time & Stage Duration Mining Subsystem

Computes per-task waiting time (task start timestamp − previous task completion timestamp)
and average task stage duration (task completion timestamp − task start timestamp) per activity.
"""

from typing import Dict, List
import pandas as pd


def calculate_per_event_waiting_times(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate waiting time in hours for each sequential event within each process instance.

    :param df: PM4Py-formatted DataFrame sorted by case and timestamp
    :return: DataFrame with added waiting_time_hours column
    """
    if df.empty:
        return df

    df_sorted = df.sort_values(by=["case:concept:name", "time:timestamp"]).copy()

    # Previous event timestamp within same process case
    df_sorted["prev_timestamp"] = df_sorted.groupby("case:concept:name")["time:timestamp"].shift(1)

    # Waiting time = current_event_time - prev_event_time
    waiting_seconds = (df_sorted["time:timestamp"] - df_sorted["prev_timestamp"]).dt.total_seconds()
    df_sorted["waiting_time_hours"] = (waiting_seconds / 3600.0).fillna(0.0)

    return df_sorted


def calculate_activity_waiting_times(df: pd.DataFrame) -> Dict[str, float]:
    """
    Compute average waiting time in hours grouped by activity/task name.

    :param df: PM4Py-formatted DataFrame
    :return: Dict mapping activity_name -> mean_waiting_time_hours
    """
    df_with_wait = calculate_per_event_waiting_times(df)
    if df_with_wait.empty or "prev_timestamp" not in df_with_wait.columns:
        return {}

    # Filter out first event of each case (which has 0 waiting time by default)
    non_first = df_with_wait[df_with_wait["prev_timestamp"].notna()]
    if non_first.empty:
        return {}

    avg_by_activity = non_first.groupby("concept:name")["waiting_time_hours"].mean()
    return {str(act): round(float(val), 4) for act, val in avg_by_activity.items()}


def calculate_activity_stage_durations(df: pd.DataFrame) -> Dict[str, float]:
    """
    Compute average task stage duration in hours (TASK_COMPLETED timestamp - TASK_STARTED timestamp)
    grouped by activity/stage name.

    :param df: PM4Py-formatted DataFrame
    :return: Dict mapping activity_name -> mean_stage_duration_hours
    """
    if df.empty:
        return {}

    df_starts = df[df["event_type"] == "TASK_STARTED"].copy()
    df_completes = df[df["event_type"] == "TASK_COMPLETED"].copy()

    if df_starts.empty or df_completes.empty:
        return {}

    merged = pd.merge(
        df_starts,
        df_completes,
        on=["case:concept:name", "task_id", "concept:name"],
        suffixes=("_start", "_complete"),
    )

    if merged.empty:
        return {}

    durations_seconds = (merged["time:timestamp_complete"] - merged["time:timestamp_start"]).dt.total_seconds()
    merged["stage_duration_hours"] = (durations_seconds / 3600.0).clip(lower=0.0)

    avg_by_activity = merged.groupby("concept:name")["stage_duration_hours"].mean()
    return {str(act): round(float(val), 4) for act, val in avg_by_activity.items()}


def calculate_average_waiting_time(df: pd.DataFrame) -> float:
    """
    Compute overall average waiting time in hours across all process tasks.

    :param df: PM4Py-formatted DataFrame
    :return: Mean waiting time in hours
    """
    df_with_wait = calculate_per_event_waiting_times(df)
    if df_with_wait.empty or "prev_timestamp" not in df_with_wait.columns:
        return 0.0
    non_first = df_with_wait[df_with_wait["prev_timestamp"].notna()]
    if non_first.empty:
        return 0.0

    mean_val = non_first["waiting_time_hours"].mean()
    return round(float(mean_val), 4)
