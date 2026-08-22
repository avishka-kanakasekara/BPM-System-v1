"""
Agent 2 — TO-BE Process Simulation Subsystem

Simulates AS-IS vs proposed TO-BE process durations and calculates predicted efficiency improvements.
"""

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class SimulationResult:
    as_is_cycle_time_hours: float
    to_be_cycle_time_hours: float
    hours_saved: float
    improvement_percentage: float
    proposed_interventions: Dict[str, Any] = field(default_factory=dict)


def simulate_to_be_process(
    as_is_bottleneck_hours: float = 18.27,
    as_is_total_cycle_hours: float = 30.68,
    target_bottleneck_hours: float = 6.0,
    rework_reduction_hours: float = 4.0,
) -> SimulationResult:
    """
    Simulate TO-BE process performance when automated SLA reminders and cost-centre validation are applied.

    :param as_is_bottleneck_hours: Current average duration of bottleneck stage (Manager Approval)
    :param as_is_total_cycle_hours: Current total process cycle time
    :param target_bottleneck_hours: Predicted bottleneck duration after automated reminders
    :param rework_reduction_hours: Predicted duration savings from pre-validation rework reduction
    :return: SimulationResult instance
    """
    bottleneck_savings = max(0.0, as_is_bottleneck_hours - target_bottleneck_hours)
    total_savings = bottleneck_savings + rework_reduction_hours

    to_be_total = max(1.0, as_is_total_cycle_hours - total_savings)
    improvement_pct = round((total_savings / float(as_is_total_cycle_hours)) * 100, 1)

    return SimulationResult(
        as_is_cycle_time_hours=round(as_is_total_cycle_hours, 2),
        to_be_cycle_time_hours=round(to_be_total, 2),
        hours_saved=round(total_savings, 2),
        improvement_percentage=improvement_pct,
        proposed_interventions={
            "automated_sla_reminders": f"Reduces Manager Approval delay from {as_is_bottleneck_hours:.1f}h to {target_bottleneck_hours:.1f}h",
            "pre_validation_cost_centre": f"Eliminates rework saving {rework_reduction_hours:.1f}h",
        },
    )
