"""
Agent 2 — KPI Analytics Tool

Reads the observational monitoring service. Does not change workflow state,
plans, or recommendations. Numbers come from persisted monitoring facts only.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.tools.schemas import CalculateKPIInput, CalculateKPIOutput
from app.company_directory.seed import BPMFLOW_DEMO_TENANT_ID


def _hours(seconds: Decimal | None) -> float:
    if seconds is None:
        return 0.0
    return float(seconds / Decimal("3600"))


async def calculate_kpi(
    session: AsyncSession | None, input_data: CalculateKPIInput
) -> CalculateKPIOutput:
    """Calculate KPIs from persisted monitoring records. Never mutates workflow."""
    del session  # observational path does not query Agent2 invented fallbacks
    from app.monitoring.service import MonitoringService

    tenant_id = BPMFLOW_DEMO_TENANT_ID
    if input_data.tenant_id:
        tenant_id = UUID(str(input_data.tenant_id))
    process_id = UUID(str(input_data.process_id)) if input_data.process_id else None
    window_end = datetime.now(UTC)
    window_start = window_end - timedelta(days=input_data.days_back)
    report = MonitoringService().kpis(
        tenant_id,
        process_id=process_id,
        window_start=window_start,
        window_end=window_end,
    )
    bottleneck = "insufficient_evidence"
    if report.bottleneck_steps:
        bottleneck = report.bottleneck_steps[0].step
    completion = 0.0 if report.completion_rate is None else float(report.completion_rate)
    return CalculateKPIOutput(
        process_type=input_data.process_type,
        avg_cycle_time_hours=_hours(report.average_completion_time_seconds),
        completion_rate=completion,
        sla_compliance_rate=0.0,
        throughput=report.completed_processes,
        bottleneck_task=bottleneck,
    )
