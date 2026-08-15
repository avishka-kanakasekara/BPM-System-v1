"""
Agent 2 — SLA Risk Predictor

Predicts SLA breach probability using an explainable weighted feature heuristic:
risk_score = 0.35*(elapsed/sla) + 0.35*(hist_avg/sla) + 0.15*workload_factor + 0.15*hist_breach_rate
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class SLARiskPrediction:
    task_id: str
    task_type: str
    breach_probability: float
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    is_at_risk: bool
    explainability_features: Dict[str, Any] = field(default_factory=dict)


def predict_sla_risk(
    task_id: str,
    task_type: str,
    elapsed_hours: float,
    sla_hours: float = 24.0,
    historical_avg_hours: float = 18.27,
    current_workload: int = 3,
    historical_breach_rate: float = 0.155,
) -> SLARiskPrediction:
    """
    Predict SLA breach risk score using explainable weighted feature heuristic.

    :param task_id: Task UUID
    :param task_type: Type of task (e.g. Manager Approval)
    :param elapsed_hours: Hours elapsed since task creation
    :param sla_hours: SLA hours limit
    :param historical_avg_hours: Historical average duration for this task type
    :param current_workload: Current pending tasks assigned to approver
    :param historical_breach_rate: Historical SLA breach rate (0.0 to 1.0)
    :return: SLARiskPrediction instance
    """
    sla = max(1.0, sla_hours)
    elapsed_ratio = min(1.5, elapsed_hours / sla)
    hist_ratio = min(1.5, historical_avg_hours / sla)
    workload_factor = min(1.0, current_workload / 5.0)

    # Calibrated weighted feature formula
    score = (
        0.35 * elapsed_ratio
        + 0.35 * hist_ratio
        + 0.15 * workload_factor
        + 0.15 * historical_breach_rate
    )
    prob = round(min(1.0, max(0.0, score)), 4)

    if prob >= 0.80:
        level = "CRITICAL"
    elif prob >= 0.60:
        level = "HIGH"
    elif prob >= 0.35:
        level = "MEDIUM"
    else:
        level = "LOW"

    return SLARiskPrediction(
        task_id=task_id,
        task_type=task_type,
        breach_probability=prob,
        risk_level=level,
        is_at_risk=(prob >= 0.60),
        explainability_features={
            "elapsed_ratio_contrib": round(0.35 * elapsed_ratio, 4),
            "historical_ratio_contrib": round(0.35 * hist_ratio, 4),
            "workload_contrib": round(0.15 * workload_factor, 4),
            "breach_rate_contrib": round(0.15 * historical_breach_rate, 4),
            "total_score": prob,
        },
    )
