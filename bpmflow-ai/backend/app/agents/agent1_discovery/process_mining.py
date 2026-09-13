"""Event-log analysis for Agent 1 using PM4Py."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pandas as pd
import pm4py

from app.agents.agent1_discovery.schemas import FlaggedException, ProcessMiningResult
from app.core.logging import get_logger

logger = get_logger(__name__)

HAPPY_PATH_PROCUREMENT = [
    "Submit Purchase Request",
    "Approve Purchase Request",
    "Create Purchase Order",
    "Receive Goods",
    "Pay Invoice",
]


def _variant_key(key) -> list[str]:
    if isinstance(key, (list, tuple)):
        return [str(activity) for activity in key]
    return [part.strip() for part in str(key).split(",") if part.strip()]


def _variant_count(value) -> int:
    if isinstance(value, int):
        return value
    return len(value)


def _most_frequent_variant(event_log) -> list[str]:
    variants = pm4py.get_variants(event_log)
    if not variants:
        return []
    best_key, _ = max(variants.items(), key=lambda item: _variant_count(item[1]))
    return _variant_key(best_key)


def _avg_waiting_times(dataframe: pd.DataFrame) -> dict[str, float]:
    """Mean wait (hours) from the previous event to this activity, per activity."""
    waits: dict[str, list[float]] = defaultdict(list)
    ordered = dataframe.sort_values(["case:concept:name", "time:timestamp"])
    for _, group in ordered.groupby("case:concept:name", sort=False):
        activities = group["concept:name"].tolist()
        times = group["time:timestamp"].tolist()
        for activity, current, previous in zip(activities[1:], times[1:], times[:-1]):
            waits[str(activity)].append((current - previous).total_seconds() / 3600.0)
    return {
        activity: round(sum(values) / len(values), 4)
        for activity, values in sorted(waits.items())
        if values
    }


def _rework_activities(dataframe: pd.DataFrame) -> list[str]:
    repeated: set[str] = set()
    case_col = "case:concept:name"
    activity_col = "concept:name"
    for _, group in dataframe.groupby(case_col, sort=False):
        counts = group[activity_col].value_counts()
        repeated.update(counts[counts > 1].index.astype(str).tolist())
    return sorted(repeated)


def _flagged_exceptions(dataframe: pd.DataFrame) -> list[FlaggedException]:
    case_col = "case:concept:name"
    time_col = "time:timestamp"
    spans = dataframe.groupby(case_col)[time_col].agg(["min", "max"])
    cycle_hours = (spans["max"] - spans["min"]).dt.total_seconds() / 3600.0
    if cycle_hours.empty:
        return []
    mean = float(cycle_hours.mean())
    std = float(cycle_hours.std(ddof=0))
    threshold = mean + 2 * std if std > 0 else mean
    flagged: list[FlaggedException] = []
    for case_id, hours in cycle_hours.items():
        if hours > threshold and std > 0:
            flagged.append(
                FlaggedException(
                    case_id=str(case_id),
                    reason="cycle_time_outlier",
                    metric="cycle_time_hours",
                    value=round(float(hours), 4),
                    threshold=round(threshold, 4),
                )
            )
    return flagged


def _activity_frequency(dataframe: pd.DataFrame) -> tuple[dict[str, int], dict[str, int], int, int]:
    """Return event counts, case counts, total cases, and total events per activity."""
    case_col = "case:concept:name"
    activity_col = "concept:name"
    event_counts = {
        str(activity): int(count)
        for activity, count in dataframe[activity_col].value_counts().items()
    }
    case_counts: dict[str, int] = defaultdict(int)
    for _, group in dataframe.groupby(case_col, sort=False):
        for activity in set(group[activity_col].astype(str).tolist()):
            case_counts[activity] += 1
    total_cases = int(dataframe[case_col].nunique())
    total_events = int(len(dataframe))
    return dict(event_counts), dict(case_counts), total_cases, total_events


def analyze_event_log(csv_path: str | Path) -> ProcessMiningResult:
    """Discover variants, waiting times, rework, and outliers from a CSV event log."""
    path = Path(csv_path)
    raw = pd.read_csv(path)
    required = {"case_id", "activity", "timestamp", "resource"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"Event log is missing columns: {sorted(missing)}")

    dataframe = pm4py.format_dataframe(
        raw,
        case_id="case_id",
        activity_key="activity",
        timestamp_key="timestamp",
    )
    event_log = pm4py.convert_to_event_log(dataframe)
    waiting = _avg_waiting_times(dataframe)
    event_counts, case_counts, total_cases, total_events = _activity_frequency(dataframe)

    result = ProcessMiningResult(
        most_frequent_variant=_most_frequent_variant(event_log),
        avg_waiting_time_per_activity=waiting,
        rework_activities=_rework_activities(dataframe),
        flagged_exceptions=_flagged_exceptions(dataframe),
        activity_event_counts=event_counts,
        activity_case_counts=case_counts,
        total_cases=total_cases,
        total_events=total_events,
        timing_available=bool(waiting),
    )
    logger.info(
        "process_mining_complete",
        extra={
            "variant_length": len(result.most_frequent_variant),
            "rework_count": len(result.rework_activities),
            "exception_count": len(result.flagged_exceptions),
            "timing_available": result.timing_available,
            "total_cases": result.total_cases,
        },
    )
    return result
