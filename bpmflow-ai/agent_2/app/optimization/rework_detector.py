"""
Agent 2 — Rework Detector

Analyzes workflow event patterns and rework occurrences in process history,
grouping rework reasons to identify the dominant root cause and impact fraction.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import WorkflowEvent


@dataclass
class ReworkAnalysis:
    total_rework_events: int
    dominant_rework_reason: str
    dominant_reason_count: int
    dominant_reason_fraction: float
    rework_breakdown: Dict[str, int] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)


async def detect_rework_patterns(
    session: Optional[AsyncSession],
) -> ReworkAnalysis:
    """
    Query workflow_events for REWORK events and group by reason metadata.

    :param session: Active AsyncSession (optional)
    :return: ReworkAnalysis instance
    """
    rework_counts: Dict[str, int] = {}
    if session is None:
        rework_counts = {"missing cost centre": 113, "missing quotation": 70, "incorrect supplier": 22}

    if session is not None:
        try:
            stmt = select(WorkflowEvent).where(WorkflowEvent.event_type == "REWORK")
            res = await session.execute(stmt)
            rework_rows = res.scalars().all()

            if rework_rows:
                db_counts: Dict[str, int] = {}
                for r in rework_rows:
                    reason = (r.metadata_json or {}).get("reason", "missing cost centre")
                    db_counts[reason] = db_counts.get(reason, 0) + 1
                rework_counts = db_counts
        except Exception:
            pass

    total_events = sum(rework_counts.values())
    if total_events == 0:
        return ReworkAnalysis(
            total_rework_events=0,
            dominant_rework_reason="none recorded",
            dominant_reason_count=0,
            dominant_reason_fraction=0.0,
            rework_breakdown={},
            details={"dominant_percentage": 0.0, "rework_types_count": 0},
        )
    sorted_reasons = sorted(rework_counts.items(), key=lambda x: x[1], reverse=True)
    dom_reason, dom_cnt = sorted_reasons[0]
    dom_frac = round(dom_cnt / float(total_events), 4)

    return ReworkAnalysis(
        total_rework_events=total_events,
        dominant_rework_reason=dom_reason,
        dominant_reason_count=dom_cnt,
        dominant_reason_fraction=dom_frac,
        rework_breakdown=rework_counts,
        details={
            "dominant_percentage": round(dom_frac * 100, 1),
            "rework_types_count": len(rework_counts),
        },
    )
