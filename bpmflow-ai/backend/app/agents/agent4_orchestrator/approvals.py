"""Human approval gate for Agent 4.

Creates PENDING approval_requests when the risk engine recommends HUMAN_APPROVAL.
Does not auto-approve, execute workflows, or change stages after a human decision.
"""

from uuid import UUID

from .constants import ApprovalStatus, RiskLevel, RiskRecommendation, WorkflowStage
from .approval_repository import ApprovalRepository
from .exceptions import DatabasePersistenceError
from .schemas import (
    ApprovalDecisionResult,
    ApprovalGateResult,
    ApprovalRequestRecord,
    RiskAssessment,
)
from .service import OrchestratorService
from .state_machine import InvalidTransitionError


class ApprovalService:
    """Applies risk findings to the human-approval gate via OrchestratorService."""

    def __init__(
        self,
        orchestrator: OrchestratorService,
        repository: ApprovalRepository,
    ) -> None:
        self._orchestrator = orchestrator
        self._repository = repository

    def requires_human_approval(self, assessment: RiskAssessment) -> bool:
        """True when at least one finding recommends HUMAN_APPROVAL."""
        return any(
            finding.recommendation is RiskRecommendation.HUMAN_APPROVAL
            for finding in assessment.findings
        )

    async def apply_risk_assessment(
        self,
        process_id: UUID,
        assessment: RiskAssessment,
        task_id: UUID | None = None,
        requested_by: UUID | None = None,
        approver_id: UUID | None = None,
    ) -> ApprovalGateResult:
        """Create a PENDING request and move RISK_REVIEW → AWAITING_HUMAN_APPROVAL.

        Raises InvalidTransitionError if the current stage cannot make that move.
        """
        if not self.requires_human_approval(assessment):
            return ApprovalGateResult(human_approval_required=False)

        if not await self._orchestrator.can_move(
            process_id,
            WorkflowStage.AWAITING_HUMAN_APPROVAL,
        ):
            current = await self._orchestrator.get_current_stage(process_id)
            raise InvalidTransitionError(
                current,
                WorkflowStage.AWAITING_HUMAN_APPROVAL,
            )

        reason = self._approval_reason(assessment)
        risk_level = self._stored_risk_level(assessment)
        try:
            approval = await self._repository.create_approval_request(
                process_id=process_id,
                risk_level=risk_level,
                reason=reason,
                task_id=task_id,
                requested_by=requested_by,
                approver_id=approver_id,
            )
            transition = await self._orchestrator.move_process(
                process_id,
                WorkflowStage.AWAITING_HUMAN_APPROVAL,
                reason=reason,
            )
            await self._repository.commit()
        except InvalidTransitionError:
            await self._safe_rollback()
            raise
        except Exception as exc:
            await self._safe_rollback()
            if isinstance(exc, DatabasePersistenceError):
                raise
            raise DatabasePersistenceError(
                f"Failed to open human approval gate for process {process_id}"
            ) from exc

        return ApprovalGateResult(
            human_approval_required=True,
            approval=approval,
            transition=transition,
        )

    async def get_approval_request(self, approval_id: UUID) -> ApprovalRequestRecord:
        return await self._repository.get_approval_request(approval_id)

    async def get_pending_approval_for_process(
        self,
        process_id: UUID,
    ) -> ApprovalRequestRecord | None:
        return await self._repository.get_pending_approval_for_process(process_id)

    async def approve_request(
        self,
        approval_id: UUID,
        approver_id: UUID,
        comments: str | None = None,
    ) -> ApprovalDecisionResult:
        """Record APPROVED. Does not advance the workflow further."""
        approval = await self._repository.approve_request(
            approval_id,
            approver_id,
            comments,
        )
        await self._repository.commit()
        return ApprovalDecisionResult(
            approval=approval,
            decision=ApprovalStatus.APPROVED,
        )

    async def reject_request(
        self,
        approval_id: UUID,
        approver_id: UUID,
        comments: str | None = None,
    ) -> ApprovalDecisionResult:
        """Record REJECTED. Does not advance the workflow further."""
        approval = await self._repository.reject_request(
            approval_id,
            approver_id,
            comments,
        )
        await self._repository.commit()
        return ApprovalDecisionResult(
            approval=approval,
            decision=ApprovalStatus.REJECTED,
        )

    def _approval_reason(self, assessment: RiskAssessment) -> str:
        relevant = [
            finding
            for finding in assessment.findings
            if finding.recommendation is RiskRecommendation.HUMAN_APPROVAL
        ]
        parts = [
            f"{finding.risk_type.value}: {finding.description}"
            for finding in relevant
        ]
        return " ".join(parts) if parts else "Human approval required."

    def _stored_risk_level(self, assessment: RiskAssessment) -> RiskLevel:
        if assessment.overall_risk_level is not None:
            return assessment.overall_risk_level
        relevant = [
            finding
            for finding in assessment.findings
            if finding.recommendation is RiskRecommendation.HUMAN_APPROVAL
        ]
        return relevant[0].risk_level

    async def _safe_rollback(self) -> None:
        try:
            await self._repository.rollback()
        except DatabasePersistenceError:
            raise
        except Exception as exc:
            raise DatabasePersistenceError(
                "Failed to roll back approval gate changes"
            ) from exc
