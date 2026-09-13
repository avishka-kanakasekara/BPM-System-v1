"""Service orchestration for Agent 3 Resource Allocation."""

import inspect
from datetime import datetime
from decimal import Decimal
from typing import Any

from .advisory import assert_advisory_recommendation
from .constants import FailureErrorCode, MessageType
from .explainer_template import ExplanationContext, TemplateExplainer
from .failures import (
    FailureSpec,
    build_failed_recommendation,
    build_internal_error_failure,
    build_resource_lookup_failure,
    detect_invalid_request,
    is_resource_lookup_error,
)
from .gaps import GapDetector
from .interfaces import ResourceRepository
from .llm_explainer import (
    ExplanationGenerator,
    ResilientFallbackExplainer,
    TemplateExplainerAdapter,
)
from .schemas import (
    AgentMessageMetadata,
    AllocationRecommendation,
    AllocationRequest,
    RecommendationStatus,
    utc_now,
    validate_timezone_aware,
)
from .strategies.budget import BudgetResourceStrategy
from .strategies.human import HumanResourceStrategy


class ResourceAllocationService:
    """Orchestrates the complete resource allocation pipeline."""

    def __init__(
        self,
        repository: ResourceRepository,
        explainer: Any | None = None,
        directory: Any | None = None,
    ):
        """Initialize with a resource repository and optional explanation generator.

        Enforces the ExplanationGenerator async protocol. Direct TemplateExplainer instances
        are explicitly wrapped via TemplateExplainerAdapter for backward compatibility.
        """
        self.repository = repository
        self.human_strategy = HumanResourceStrategy(repository, directory=directory)
        self.budget_strategy = BudgetResourceStrategy(repository)
        self.gap_detector = GapDetector()
        self.directory = directory

        if explainer is None:
            self.explainer: ExplanationGenerator = ResilientFallbackExplainer()
        elif isinstance(explainer, TemplateExplainer):
            self.explainer = TemplateExplainerAdapter(explainer)
        elif hasattr(explainer, "generate_explanation") and callable(explainer.generate_explanation):
            if not inspect.iscoroutinefunction(explainer.generate_explanation):
                self.explainer = TemplateExplainerAdapter(explainer)
            else:
                self.explainer = explainer
        else:
            raise TypeError("explainer must implement ExplanationGenerator async protocol")

    async def process_allocation_request(
        self,
        request: AllocationRequest,
        evaluation_timestamp: datetime | None = None,
    ) -> AllocationRecommendation:
        """Process a resource allocation request.

        Business constraint outcomes return PENDING_HUMAN_APPROVAL.
        Technical failures return FAILED. This method never raises.
        """
        response_metadata: AgentMessageMetadata | None = None

        try:
            if evaluation_timestamp is None:
                evaluation_timestamp = utc_now()
            else:
                validate_timezone_aware(evaluation_timestamp, "evaluation_timestamp")

            response_metadata = self._build_response_metadata(request.metadata)

            invalid_request = detect_invalid_request(request, evaluation_timestamp)
            if invalid_request is not None:
                return build_failed_recommendation(response_metadata, invalid_request)

            request = self._bind_requester_identity(request)
            identity_failure = self._identity_failure(request)
            if identity_failure is not None:
                return build_failed_recommendation(response_metadata, identity_failure)

            human_result = None
            if request.human_requirements is not None:
                try:
                    human_result = await self.human_strategy.process_requirement(
                        requirement=request.human_requirements,
                        tenant_id=request.metadata.tenant_id,
                        evaluation_timestamp=evaluation_timestamp,
                    )
                except Exception as exc:
                    if is_resource_lookup_error(exc):
                        return build_resource_lookup_failure(
                            response_metadata,
                            str(exc),
                        )
                    return build_internal_error_failure(response_metadata)
                if (
                    human_result is not None
                    and human_result.outcome_code == "APPROVER_NOT_RESOLVED"
                    and request.human_requirements.assignment_kind == "approver"
                ):
                    return build_failed_recommendation(
                        response_metadata,
                        FailureSpec(
                            error_code=FailureErrorCode.APPROVER_NOT_RESOLVED,
                            error_message="APPROVER_NOT_RESOLVED",
                        ),
                    )

            budget_result = None
            if request.budget_requirements is not None:
                try:
                    budget_result = await self.budget_strategy.process_requirement(
                        requirement=request.budget_requirements,
                        tenant_id=request.metadata.tenant_id,
                        evaluation_timestamp=evaluation_timestamp,
                    )
                except Exception as exc:
                    if is_resource_lookup_error(exc):
                        return build_resource_lookup_failure(
                            response_metadata,
                            str(exc),
                        )
                    return build_internal_error_failure(response_metadata)

            return await self._build_business_recommendation(
                response_metadata=response_metadata,
                human_result=human_result,
                budget_result=budget_result,
                request=request,
            )
        except Exception:
            if response_metadata is None:
                response_metadata = self._build_response_metadata(request.metadata)
            return build_internal_error_failure(response_metadata)

    async def _build_business_recommendation(
        self,
        response_metadata: AgentMessageMetadata,
        human_result,
        budget_result,
        request: AllocationRequest | None = None,
    ) -> AllocationRecommendation:
        """Build a completed business recommendation, including constraint outcomes."""
        resource_gaps = []
        alternatives = []
        limitations = []

        if human_result is not None:
            human_gaps, human_alternatives, human_limitations = (
                self.gap_detector.analyze_human_constraint(human_result)
            )
            resource_gaps.extend(human_gaps)
            alternatives.extend(human_alternatives)
            limitations.extend(human_limitations)

        if budget_result is not None:
            budget_gaps, budget_limitations = self.gap_detector.analyze_budget_constraint(
                budget_result
            )
            resource_gaps.extend(budget_gaps)
            limitations.extend(budget_limitations)

        confidence = self._calculate_confidence(human_result, budget_result)
        currency = request.budget_requirements.currency if (request and request.budget_requirements) else None
        explanation_context = ExplanationContext(
            human_requirement_result=human_result,
            budget_requirement_result=budget_result,
            resource_gaps=resource_gaps,
            alternatives=alternatives,
            limitations=limitations,
            confidence=confidence,
            currency=currency,
        )
        explanation = await self.explainer.generate_explanation(explanation_context)

        recommendation = AllocationRecommendation(
            metadata=response_metadata,
            status=RecommendationStatus.PENDING_HUMAN_APPROVAL,
            human_requirement_result=human_result,
            budget_requirement_result=budget_result,
            resource_gaps=resource_gaps,
            alternatives=alternatives,
            explanation=explanation,
            requires_human_approval=True,
            manual_intervention_required=False,
            confidence=confidence,
            limitations=limitations,
        )
        assert_advisory_recommendation(recommendation)
        return recommendation

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

    def _bind_requester_identity(self, request: AllocationRequest) -> AllocationRequest:
        human = request.human_requirements
        if human is None or self.directory is None or human.requester_employee_id is not None:
            return request
        employee = self.directory.resolve_employee_by_user_id(
            tenant_id=request.metadata.tenant_id,
            user_id=human.requester_id,
        )
        if employee is None:
            return request
        return request.model_copy(
            update={
                "human_requirements": human.model_copy(
                    update={"requester_employee_id": employee.employee_id}
                )
            }
        )

    def _identity_failure(self, request: AllocationRequest) -> FailureSpec | None:
        human = request.human_requirements
        if human is None or not human.require_requester_identity:
            return None
        if human.requester_employee_id is not None:
            return None
        return FailureSpec(
            error_code=FailureErrorCode.IDENTITY_NOT_RESOLVED,
            error_message="Authenticated requester is not mapped to a company employee",
        )
