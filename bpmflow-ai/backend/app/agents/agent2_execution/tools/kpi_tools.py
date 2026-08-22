"""
Agent 2 — KPI Analytics Tool (Real DB Query)

Provides calculate_kpi querying Agent 2 DB tables to calculate cycle time, completion rate, throughput, and bottleneck task.
"""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.analytics import kpi_engine
from app.agents.agent2_execution.tools.schemas import CalculateKPIInput, CalculateKPIOutput


async def calculate_kpi(
    session: Optional[AsyncSession], input_data: CalculateKPIInput
) -> CalculateKPIOutput:
    """Calculate aggregated KPI analytics metrics from historical DB records."""
    metrics = await kpi_engine.get_kpis(session, process_id=None)
    avg_cycle = metrics.get("average_cycle_time") or 0.0
    completion = metrics.get("task_success_rate")
    sla = metrics.get("sla_compliance_rate")
    throughput = int(metrics.get("throughput") or 0)
    bottleneck = metrics.get("bottleneck_task") or "Unknown"

    if session is None and avg_cycle <= 0:
        avg_cycle = 1.0
        completion = 1.0
        sla = 1.0
        bottleneck = "Insufficient history"

    return CalculateKPIOutput(
        process_type=input_data.process_type,
        avg_cycle_time_hours=float(avg_cycle or 1.0),
        completion_rate=float(completion if completion is not None else 1.0),
        sla_compliance_rate=float(sla if sla is not None else 1.0),
        throughput=throughput,
        bottleneck_task=str(bottleneck),
    )
