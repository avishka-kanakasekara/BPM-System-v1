"""API schemas for approval resources."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.agents.agent4_orchestrator.constants import ApprovalStatus, RiskLevel
from app.agents.agent4_orchestrator.schemas import ApprovalDecisionResult, ApprovalRequestRecord


class ApprovalResponse(BaseModel):
    """Approval request exposed to API clients."""

    id: UUID
    process_id: UUID
    task_id: Optional[UUID] = None
    requested_by: Optional[UUID] = None
    approver_id: Optional[UUID] = None
    status: ApprovalStatus
    risk_level: RiskLevel
    reason: str = Field(min_length=1)
    decision: Optional[ApprovalStatus] = None
    comments: Optional[str] = None
    created_at: datetime
    decided_at: Optional[datetime] = None


class ApprovalDecisionRequest(BaseModel):
    """Human decision payload for approve/reject endpoints."""

    comments: Optional[str] = None


class ApprovalDecisionResponse(BaseModel):
    """Outcome of approve/reject. Does not include workflow execution."""

    approval: ApprovalResponse
    decision: ApprovalStatus


def approval_from_record(record: ApprovalRequestRecord) -> ApprovalResponse:
    """Map Agent 4 approval record to an API response schema."""
    return ApprovalResponse.model_validate(record.model_dump())


def decision_from_result(result: ApprovalDecisionResult) -> ApprovalDecisionResponse:
    """Map Agent 4 decision result to an API response schema."""
    return ApprovalDecisionResponse(
        approval=approval_from_record(result.approval),
        decision=result.decision,
    )
