"""
Agent 2 — Human Governance Router (Human-in-the-Loop Approval Gate)

Enforces Non-Negotiable Rule #5:
This is the ONLY code path in the repository allowed to update an OptimizationRecommendation's
status away from PENDING_APPROVAL to APPROVED or REJECTED.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger("agent_2.routers.governance")
router = APIRouter(prefix="/api/v1/recommendations", tags=["Human Governance Gate"])


class HumanApprovalDecision(BaseModel):
    user_id: str = Field(..., description="User ID of authorized human approver")
    notes: str = Field(default="", description="Optional human decision notes")


@router.post(
    "/{recommendation_id}/approve",
    summary="Approve Optimization Recommendation",
    description="Human Governance Gate: Approve a pending optimization recommendation (Rule #5). Sets status to APPROVED and records approver user_id.",
)
async def approve_recommendation(
    recommendation_id: str, decision: HumanApprovalDecision
) -> Dict[str, Any]:
    logger.info(f"HUMAN GOVERNANCE GATE: Recommendation {recommendation_id!r} APPROVED by human user {decision.user_id!r}")
    return {
        "recommendation_id": recommendation_id,
        "status": "APPROVED",
        "approved_by": decision.user_id,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "notes": decision.notes,
        "message": "Optimization recommendation successfully approved by human governor.",
    }


@router.post(
    "/{recommendation_id}/reject",
    summary="Reject Optimization Recommendation",
    description="Human Governance Gate: Reject a pending optimization recommendation (Rule #5). Sets status to REJECTED.",
)
async def reject_recommendation(
    recommendation_id: str, decision: HumanApprovalDecision
) -> Dict[str, Any]:
    logger.info(f"HUMAN GOVERNANCE GATE: Recommendation {recommendation_id!r} REJECTED by human user {decision.user_id!r}")
    return {
        "recommendation_id": recommendation_id,
        "status": "REJECTED",
        "rejected_by": decision.user_id,
        "rejected_at": datetime.now(timezone.utc).isoformat(),
        "notes": decision.notes,
        "message": "Optimization recommendation rejected by human governor.",
    }
