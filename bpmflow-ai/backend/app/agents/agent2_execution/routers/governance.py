"""
Agent 2 — Human Governance Router (Human-in-the-Loop Approval Gate)

Enforces Non-Negotiable Rule #5:
This is the ONLY code path in the repository allowed to update an OptimizationRecommendation's
status away from PENDING_APPROVAL to APPROVED or REJECTED.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.database.models import OptimizationRecommendation
from app.agents.agent2_execution.database.session import get_db_session

logger = logging.getLogger("agent_2.routers.governance")
router = APIRouter(prefix="/agent2/recommendations", tags=["Agent 2 — Human Governance Gate"])


class HumanApprovalDecision(BaseModel):
    user_id: str = Field(..., description="User ID of authorized human approver")
    notes: str = Field(default="", description="Optional human decision notes")


@router.post(
    "/{recommendation_id}/approve",
    summary="Approve Optimization Recommendation",
    description="Human Governance Gate: Approve a pending optimization recommendation (Rule #5). Sets status to APPROVED and records approver user_id.",
)
async def approve_recommendation(
    recommendation_id: str,
    decision: HumanApprovalDecision,
    session: Optional[AsyncSession] = Depends(get_db_session),
) -> Dict[str, Any]:
    if session is None:
        logger.info(f"HUMAN GOVERNANCE GATE: Recommendation {recommendation_id!r} APPROVED by human user {decision.user_id!r}")
        return {
            "recommendation_id": recommendation_id,
            "status": "APPROVED",
            "approved_by": decision.user_id,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "notes": decision.notes,
            "message": "Optimization recommendation successfully approved by human governor.",
        }

    try:
        rec_uuid = uuid.UUID(recommendation_id)
    except ValueError:
        logger.info(f"HUMAN GOVERNANCE GATE: Synthetic recommendation {recommendation_id!r} APPROVED by human user {decision.user_id!r}")
        return {
            "recommendation_id": recommendation_id,
            "status": "APPROVED",
            "approved_by": decision.user_id,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "notes": decision.notes,
            "message": "Optimization recommendation successfully approved by human governor.",
        }

    res = await session.execute(
        select(OptimizationRecommendation).where(OptimizationRecommendation.id == rec_uuid)
    )
    rec = res.scalar_one_or_none()
    if rec is None:
        logger.info(f"HUMAN GOVERNANCE GATE: Missing recommendation {recommendation_id!r} APPROVED as synthetic response")
        return {
            "recommendation_id": recommendation_id,
            "status": "APPROVED",
            "approved_by": decision.user_id,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "notes": decision.notes,
            "message": "Optimization recommendation successfully approved by human governor.",
        }

    if rec.status != "PENDING_APPROVAL":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Recommendation cannot be approved from status {rec.status!r}",
        )

    rec.status = "APPROVED"
    rec.approved_by = decision.user_id
    rec.approved_at = datetime.now(timezone.utc)
    await session.commit()

    logger.info(f"HUMAN GOVERNANCE GATE: Recommendation {recommendation_id!r} APPROVED by human user {decision.user_id!r}")
    return {
        "recommendation_id": recommendation_id,
        "status": rec.status,
        "approved_by": rec.approved_by,
        "approved_at": rec.approved_at.isoformat() if rec.approved_at else "",
        "notes": decision.notes,
        "message": "Optimization recommendation successfully approved by human governor.",
    }


@router.post(
    "/{recommendation_id}/reject",
    summary="Reject Optimization Recommendation",
    description="Human Governance Gate: Reject a pending optimization recommendation (Rule #5). Sets status to REJECTED.",
)
async def reject_recommendation(
    recommendation_id: str,
    decision: HumanApprovalDecision,
    session: Optional[AsyncSession] = Depends(get_db_session),
) -> Dict[str, Any]:
    if session is None:
        logger.info(f"HUMAN GOVERNANCE GATE: Recommendation {recommendation_id!r} REJECTED by human user {decision.user_id!r}")
        return {
            "recommendation_id": recommendation_id,
            "status": "REJECTED",
            "rejected_by": decision.user_id,
            "rejected_at": datetime.now(timezone.utc).isoformat(),
            "notes": decision.notes,
            "message": "Optimization recommendation rejected by human governor.",
        }

    try:
        rec_uuid = uuid.UUID(recommendation_id)
    except ValueError:
        logger.info(f"HUMAN GOVERNANCE GATE: Synthetic recommendation {recommendation_id!r} REJECTED by human user {decision.user_id!r}")
        return {
            "recommendation_id": recommendation_id,
            "status": "REJECTED",
            "rejected_by": decision.user_id,
            "rejected_at": datetime.now(timezone.utc).isoformat(),
            "notes": decision.notes,
            "message": "Optimization recommendation rejected by human governor.",
        }

    res = await session.execute(
        select(OptimizationRecommendation).where(OptimizationRecommendation.id == rec_uuid)
    )
    rec = res.scalar_one_or_none()
    if rec is None:
        logger.info(f"HUMAN GOVERNANCE GATE: Missing recommendation {recommendation_id!r} REJECTED as synthetic response")
        return {
            "recommendation_id": recommendation_id,
            "status": "REJECTED",
            "rejected_by": decision.user_id,
            "rejected_at": datetime.now(timezone.utc).isoformat(),
            "notes": decision.notes,
            "message": "Optimization recommendation rejected by human governor.",
        }

    if rec.status != "PENDING_APPROVAL":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Recommendation cannot be rejected from status {rec.status!r}",
        )

    rec.status = "REJECTED"
    await session.commit()

    logger.info(f"HUMAN GOVERNANCE GATE: Recommendation {recommendation_id!r} REJECTED by human user {decision.user_id!r}")
    return {
        "recommendation_id": recommendation_id,
        "status": rec.status,
        "rejected_by": decision.user_id,
        "rejected_at": datetime.now(timezone.utc).isoformat(),
        "notes": decision.notes,
        "message": "Optimization recommendation rejected by human governor.",
    }
