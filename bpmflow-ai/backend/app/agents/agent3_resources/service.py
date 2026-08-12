"""Service orchestration for Agent 3 Resource Allocation."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from .interfaces import ResourceRepository
from .schemas import (
    AllocationRequest,
    AllocationRecommendation,
    AgentMessageMetadata,
    RecommendationStatus,
    utc_now,
    validate_timezone_aware,
)
from .strategies.human import HumanResourceStrategy
from .strategies.budget import BudgetResourceStrategy
from .gaps import GapDetector
from .explainer_template import TemplateExplainer
from .constants import MessageType
from .failures import (
    detect_invalid_request,
    detect_human_failure,
    detect_budget_failure,
    build_failed_recommendation,
    build_resource_lookup_failure,
    FailureSpec,
)


class ResourceAllocationService:
    """Orchestrates the complete resource allocation pipeline."""

    def __init__(self, repository: ResourceRepository):
        """Initialize with a resource repository."""
        self.repository = repository
        self.human_strategy = HumanResourceStrategy(repository)
        self.budget_strategy = BudgetResourceStrategy(repository)
        self.gap_detector = GapDetector()
        self.explainer = TemplateExplainer()

    async def process_allocation_request(
        self,
        request: AllocationRequest,
        evaluation_timestamp: Optional[datetime] = None,
    ) -> AllocationRecommendation:
        """Process a resource allocation request.

        Every domain-level failure is returned as a schema-valid FAILED
        recommendation. This method never raises unhandled exceptions.
        """
        response_metadata: Optional[AgentMessageMetadata] = None

        try:
            if evaluation_timestamp is None:
                evaluation_timestamp = utc_now()
            else:
                validate_timezone_aware(evaluation_timestamp, "evaluation_timestamp")

            response_metadata = self._build_response_metadata(request.metadata)

            invalid_request = detect_invalid_request(request, evaluation_timestamp)
            if invalid_request is not None:
                return build_failed_recommendation(
                    request.metadata,
                    response_metadata,
                    invalid_request,
                )

            human_result = None
            if request.human_requirements is not None:
                try:
                    human_result = await self.human_strategy.process_requirement(
                        requirement=request.human_requirements,
                        evaluation_timestamp=evaluation_timestamp,
                    )
                except Exception as exc:
                    return build_resource_lookup_failure(
                        request.metadata,
                        response_metadata,
                        str(exc),
                    )

                human_failure = detect_human_failure(human_result)
                if human_failure is not None:
                    return build_failed_recommendation(
                        request.metadata,
                        response_metadata,
                        human_failure,
                    )

            budget_result = None
            if request.budget_requirements is not None:
                try:
                    budget_result = await self.budget_strategy.process_requirement(
                        requirement=request.budget_requirements,
                        evaluation_timestamp=evaluation_timestamp,
                    )
                except Exception as exc:
                    return build_resource_lookup_failure(
                        request.metadata,
                        response_metadata,
                        str(exc),
                    )

                budget_failure = detect_budget_failure(budget_result)
                if budget_failure is not None:
                    return build_failed_recommendation(
                        request.metadata,
                        response_metadata,
                        budget_failure,
                    )

            return self._build_success_recommendation(
                request_metadata=request.metadata,
                response_metadata=response_metadata,
                human_result=human_result,
                budget_result=budget_result,
            )
        except Exception as exc:
            if response_metadata is None:
                response_metadata = self._build_response_metadata(request.metadata)
            return build_resource_lookup_failure(
                request.metadata,
                response_metadata,
                str(exc),
            )

    def _build_success_recommendation(
        self,
        request_metadata: AgentMessageMetadata,
        response_metadata: AgentMessageMetadata,
        human_result,
        budget_result,
    ) -> AllocationRecommendation:
        """Build a successful PENDING_HUMAN_APPROVAL recommendation."""
        resource_gaps = []
        alternatives = []
        limitations = []

        if human_result and len(human_result.eligible_candidates) == 0:
            gap = self.gap_detector.detect_human_resource_gap(human_result)
            if gap:
                resource_gaps.append(gap)
                alternatives = self.gap_detector.generate_alternatives(
                    resource_type=human_result.resource_type,
                )
                limitations.append("No eligible HUMAN resources found for this requirement")

        confidence = self._calculate_confidence(human_result, budget_result)
        explanation_context = AllocationRecommendation.model_construct(
            metadata=response_metadata,
            status=RecommendationStatus.PENDING_HUMAN_APPROVAL,
            human_requirement_result=human_result,
            budget_requirement_result=budget_result,
            resource_gaps=resource_gaps,
            alternatives=alternatives,
            explanation="",
            requires_human_approval=True,
            confidence=confidence,
            limitations=limitations,
        )
        explanation = self.explainer.generate_explanation(explanation_context)

        return AllocationRecommendation(
            metadata=response_metadata,
            status=RecommendationStatus.PENDING_HUMAN_APPROVAL,
            human_requirement_result=human_result,
            budget_requirement_result=budget_result,
            resource_gaps=resource_gaps,
            alternatives=alternatives,
            explanation=explanation,
            requires_human_approval=True,
            confidence=confidence,
            limitations=limitations,
        )

    def _build_response_metadata(
        self,
        request_metadata: AgentMessageMetadata,
    ) -> AgentMessageMetadata:
        """Build response metadata preserving correlation_id."""
        return AgentMessageMetadata(
            correlation_id=request_metadata.correlation_id,
            process_instance_id=request_metadata.process_instance_id,
            task_id=request_metadata.task_id,
            tenant_id=request_metadata.tenant_id,
            message_type=MessageType.RESOURCE_ALLOCATION_RESPONSE,
            timestamp=utc_now(),
        )

    def _calculate_confidence(
        self,
        human_result,
        budget_result,
    ) -> Decimal:
        """Calculate confidence based on results."""
        confidence = Decimal("1.0")

        if human_result and len(human_result.eligible_candidates) == 0:
            confidence -= Decimal("0.3")

        if budget_result and budget_result.budget_validation:
            validation = budget_result.budget_validation
            if not validation.sufficient_balance:
                confidence -= Decimal("0.2")
            if not validation.currency_match:
                confidence -= Decimal("0.1")

        confidence = max(Decimal("0"), min(Decimal("1"), confidence))

        return confidence.quantize(Decimal("0.01"))
