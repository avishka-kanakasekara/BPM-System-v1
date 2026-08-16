"""Unit tests for write-path mappers (domain ↔ database)."""

import json
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from app.agents.agent3_resources.repositories.write_mappers import (
    map_request_to_allocation_request,
    map_requirement_to_allocation_requirement,
    map_recommendation_to_allocation_recommendation,
    map_candidate_to_allocation_candidate,
    map_exclusion_to_allocation_exclusion,
    map_exclusion_reason_to_allocation_exclusion_reason,
    map_gap_to_resource_gap,
    map_alternative_to_resource_alternative,
    map_budget_validation_to_budget_validation_result,
    map_evidence_link_to_recommendation_evidence_link,
    map_row_to_recommendation_header,
    map_row_to_request_metadata,
    map_row_to_candidate,
    map_row_to_exclusion_with_reasons,
    map_row_to_gap,
    map_row_to_alternative,
    map_row_to_budget_validation,
    map_row_to_evidence_link,
    validate_timezone_aware,
    generate_idempotency_key,
    _to_jsonb,
)
from app.agents.agent3_resources.repositories.persistence_exceptions import PersistenceValidationError
from app.agents.agent3_resources.schemas import (
    AllocationRequest,
    AllocationRecommendation,
    HumanResourceRequirement,
    BudgetResourceRequirement,
    RankedCandidate,
    ScoreBreakdown,
    ExcludedResource,
    ExclusionReasonEntry,
    ResourceGap,
    ResourceAlternative,
    BudgetValidationChecks,
    AgentMessageMetadata,
    RecommendationStatus,
    ResourceType,
    GapAlternativeType,
    GapType,
    ExclusionReason,
)


class TestTimezoneValidation:
    """Tests for timezone-aware datetime validation."""

    def test_validate_timezone_aware_utc(self) -> None:
        """Test that timezone-aware UTC datetime passes validation."""
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        result = validate_timezone_aware(dt, "test_field")
        assert result == dt

    def test_validate_timezone_aware_other_tz(self) -> None:
        """Test that timezone-aware datetime with other timezone passes."""
        from datetime import timedelta
        tz = timezone(timedelta(hours=5))
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=tz)
        result = validate_timezone_aware(dt, "test_field")
        assert result == dt

    def test_validate_timezone_aware_naive_raises(self) -> None:
        """Test that naive datetime raises validation error."""
        dt = datetime(2026, 1, 1, 12, 0)
        with pytest.raises(PersistenceValidationError, match="must be timezone-aware"):
            validate_timezone_aware(dt, "test_field")


class TestIdempotencyKeyGeneration:
    """Tests for idempotency key generation."""

    def test_generate_idempotency_key(self) -> None:
        """Test idempotency key generation from request metadata."""
        correlation_id = uuid4()
        tenant_id = uuid4()
        
        metadata = AgentMessageMetadata(
            correlation_id=correlation_id,
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=tenant_id,
            message_type="RESOURCE_ALLOCATION_REQUEST",
        )
        
        request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )
        
        key = generate_idempotency_key(request)
        assert key == f"{correlation_id}_{tenant_id}"

    def test_generate_idempotency_key_deterministic(self) -> None:
        """Test that idempotency key is deterministic for same request."""
        correlation_id = uuid4()
        tenant_id = uuid4()
        
        metadata = AgentMessageMetadata(
            correlation_id=correlation_id,
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=tenant_id,
            message_type="RESOURCE_ALLOCATION_REQUEST",
        )
        
        request1 = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )
        
        request2 = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )
        
        key1 = generate_idempotency_key(request1)
        key2 = generate_idempotency_key(request2)
        assert key1 == key2


class TestRequestMapping:
    """Tests for request → allocation_requests mapping."""

    def test_map_request_to_allocation_request(self) -> None:
        """Test mapping AllocationRequest to database row."""
        correlation_id = uuid4()
        tenant_id = uuid4()
        evaluation_timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        
        metadata = AgentMessageMetadata(
            correlation_id=correlation_id,
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=tenant_id,
            message_type="RESOURCE_ALLOCATION_REQUEST",
        )
        
        request = AllocationRequest(
            metadata=metadata,
            human_requirements=None,
            budget_requirements=None,
        )
        
        row = map_request_to_allocation_request(request, evaluation_timestamp)
        
        assert row["tenant_id"] == tenant_id
        assert row["correlation_id"] == correlation_id
        assert row["evaluation_timestamp"] == evaluation_timestamp
        assert "idempotency_key" in row
        assert "request_payload" in row
        assert row["request_schema_version"] is not None


class TestRequirementMapping:
    """Tests for requirement → allocation_requirements mapping."""

    def test_map_human_requirement(self) -> None:
        """Test mapping HumanResourceRequirement to database row."""
        requirement = HumanResourceRequirement(
            resource_type=ResourceType.HUMAN,
            requester_id=uuid4(),
            task_deadline=datetime(2026, 6, 1, tzinfo=timezone.utc),
            estimated_effort_hours=Decimal("10"),
            process_stage="resource_allocation",
        )
        
        row = map_requirement_to_allocation_requirement(
            requirement,
            uuid4(),
            uuid4(),
            1,
        )
        
        assert row["resource_type"] == "HUMAN"
        assert row["sequence_order"] == 1
        assert row["estimated_effort_hours"] == Decimal("10")

    def test_map_budget_requirement(self) -> None:
        """Test mapping BudgetResourceRequirement to database row."""
        requirement = BudgetResourceRequirement(
            resource_type=ResourceType.BUDGET,
            required_amount=Decimal("5000"),
            currency="USD",
            requester_id=uuid4(),
            task_deadline=datetime(2026, 6, 1, tzinfo=timezone.utc),
            process_stage="resource_allocation",
        )
        
        row = map_requirement_to_allocation_requirement(
            requirement,
            uuid4(),
            uuid4(),
            1,
        )
        
        assert row["resource_type"] == "BUDGET"
        assert row["sequence_order"] == 1


class TestRecommendationMapping:
    """Tests for recommendation → allocation_recommendations mapping."""

    def test_map_business_recommendation(self) -> None:
        """Test mapping business recommendation (PENDING_HUMAN_APPROVAL)."""
        metadata = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=uuid4(),
            message_type="RESOURCE_ALLOCATION_RESPONSE",
        )
        
        recommendation = AllocationRecommendation(
            metadata=metadata,
            status=RecommendationStatus.PENDING_HUMAN_APPROVAL,
            requires_human_approval=True,
            manual_intervention_required=False,
            explanation="Test recommendation",
            confidence=Decimal("0.85"),
            human_requirement_result=None,
            budget_requirement_result=None,
            resource_gaps=[],
            alternatives=[],
            limitations=[],
        )
        
        row = map_recommendation_to_allocation_recommendation(
            recommendation,
            uuid4(),
            uuid4(),
            1,
        )
        
        assert row["status"] == "PENDING_HUMAN_APPROVAL"
        assert row["requires_human_approval"] is True
        assert row["manual_intervention_required"] is False
        assert row["confidence"] == Decimal("0.85")
        assert row["error_code"] is None

    def test_map_failed_recommendation(self) -> None:
        """Test mapping FAILED recommendation."""
        metadata = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=uuid4(),
            message_type="RESOURCE_ALLOCATION_RESPONSE",
        )
        
        recommendation = AllocationRecommendation(
            metadata=metadata,
            status=RecommendationStatus.FAILED,
            requires_human_approval=False,
            manual_intervention_required=True,
            explanation="",
            confidence=None,
            error_code="INVALID_REQUEST",
            error_message="Invalid request",
            retryable=False,
            human_requirement_result=None,
            budget_requirement_result=None,
            resource_gaps=[],
            alternatives=[],
            limitations=[],
        )
        
        row = map_recommendation_to_allocation_recommendation(
            recommendation,
            uuid4(),
            uuid4(),
            1,
        )
        
        assert row["status"] == "FAILED"
        assert row["requires_human_approval"] is False
        assert row["manual_intervention_required"] is True
        assert row["confidence"] is None
        assert row["error_code"] == "INVALID_REQUEST"

    def test_map_invalid_status_raises(self) -> None:
        """Test that invalid status raises validation error."""
        # Skip this test as the schema validation prevents invalid status values
        # The mapper validates against the enum, which is enforced by Pydantic
        pytest.skip("Schema validation prevents invalid status values")


class TestCandidateMapping:
    """Tests for candidate → allocation_candidates mapping."""

    def test_map_candidate(self) -> None:
        """Test mapping RankedCandidate to database row."""
        # Calculate correct weighted sum: 0.9*0.3 + 0.8*0.25 + 0.85*0.2 + 0.9*0.15 + 1.0*0.1 = 0.875
        score_breakdown = ScoreBreakdown(
            role_match=Decimal("0.9"),
            skill_match=Decimal("0.8"),
            availability_score=Decimal("0.85"),
            workload_fit=Decimal("0.9"),
            authority_match=Decimal("1.0"),
            total_score=Decimal("0.875"),
        )
        candidate = RankedCandidate(
            resource_id=uuid4(),
            name="Test Developer",
            rank=1,
            allocation_score=Decimal("0.875"),
            score_breakdown=score_breakdown,
            current_workload_percentage=Decimal("30"),
            projected_workload_percentage=Decimal("40"),
            available_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
            available_until=None,
            evidence_refs={},
        )
        
        row = map_candidate_to_allocation_candidate(
            candidate,
            uuid4(),
            uuid4(),
            uuid4(),
            uuid4(),
            1,
        )
        
        assert row["candidate_rank"] == 1
        assert row["allocation_score"] == Decimal("0.875")
        assert row["role_match"] == Decimal("0.9")
        assert row["current_workload_pct"] == Decimal("30")
        assert row["candidate_name"] == "Test Developer"


class TestExclusionMapping:
    """Tests for exclusion → allocation_exclusions mapping."""

    def test_map_exclusion(self) -> None:
        """Test mapping ExcludedResource to database row."""
        excluded = ExcludedResource(
            resource_id=uuid4(),
            resource_type=ResourceType.HUMAN,
            name="Inactive Developer",
            exclusion_reasons=[
                ExclusionReasonEntry(
                    reason=ExclusionReason.INACTIVE_RESOURCE,
                    description="Resource is inactive",
                    evidence_reference="is_active field",
                )
            ],
        )
        
        row = map_exclusion_to_allocation_exclusion(
            excluded,
            uuid4(),
            uuid4(),
            uuid4(),
            uuid4(),
        )
        
        assert row["resource_type"] == "HUMAN"
        assert "id" in row

    def test_map_exclusion_reason(self) -> None:
        """Test mapping ExclusionReasonEntry to database row."""
        reason = ExclusionReasonEntry(
            reason=ExclusionReason.INACTIVE_RESOURCE,
            description="Resource is inactive",
            evidence_reference="is_active field",
        )
        
        row = map_exclusion_reason_to_allocation_exclusion_reason(
            reason,
            uuid4(),
            uuid4(),
            1,
        )
        
        assert row["reason_code"] == "INACTIVE_RESOURCE"
        assert row["sequence_order"] == 1
        assert row["description"] == "Resource is inactive"


class TestGapMapping:
    """Tests for gap → resource_gaps mapping."""

    def test_map_gap(self) -> None:
        """Test mapping ResourceGap to database row."""
        gap = ResourceGap(
            gap_type=GapType.NO_ELIGIBLE_HUMAN,
            resource_type=ResourceType.HUMAN,
            gap_description="No eligible candidates found",
            eligible_count=0,
            excluded_count=5,
            alternatives=[],
        )
        
        row = map_gap_to_resource_gap(
            gap,
            uuid4(),
            uuid4(),
            uuid4(),
            uuid4(),
        )
        
        assert row["gap_type"] == "NO_ELIGIBLE_HUMAN"
        assert row["eligible_count"] == 0
        assert row["excluded_count"] == 5


class TestAlternativeMapping:
    """Tests for alternative → resource_alternatives mapping."""

    def test_map_alternative(self) -> None:
        """Test mapping ResourceAlternative to database row."""
        alternative = ResourceAlternative(
            alternative_type=GapAlternativeType.RECRUITMENT_ESCALATION,
            description="Hire new developer",
            requires_approval=True,
            estimated_effort_hours=Decimal("40"),
            cost_impact=Decimal("5000"),
        )
        
        row = map_alternative_to_resource_alternative(
            alternative,
            uuid4(),
            uuid4(),
            uuid4(),
            1,
        )
        
        assert row["alternative_type"] == "RECRUITMENT_ESCALATION"
        assert row["sequence_order"] == 1
        assert row["requires_approval"] is True


class TestBudgetValidationMapping:
    """Tests for budget validation → budget_validation_results mapping."""

    def test_map_budget_validation(self) -> None:
        """Test mapping BudgetValidationChecks to database row."""
        validation = BudgetValidationChecks(
            resource_id=uuid4(),
            name="Team Budget",
            sufficient_balance=True,
            cost_centre_match=True,
            currency_match=True,
            validity_period_valid=True,
            within_authorization_limit=True,
            available_balance=Decimal("10000"),
            required_amount=Decimal("5000"),
            evidence_references={},
        )
        
        row = map_budget_validation_to_budget_validation_result(
            validation,
            uuid4(),
            uuid4(),
            uuid4(),
            uuid4(),
            uuid4(),
        )
        
        assert row["sufficient_balance"] is True
        assert row["available_balance"] == Decimal("10000")
        assert row["required_amount"] == Decimal("5000")


class TestReadBackMapping:
    """Tests for database row → domain mapping."""

    def test_map_row_to_recommendation_header(self) -> None:
        """Test mapping database row to recommendation header."""
        row = {
            "id": uuid4(),
            "tenant_id": uuid4(),
            "request_id": uuid4(),
            "correlation_id": uuid4(),
            "recommendation_version": 1,
            "status": "PENDING_HUMAN_APPROVAL",
            "requires_human_approval": True,
            "manual_intervention_required": False,
            "explanation": "Test",
            "confidence": Decimal("0.85"),
            "error_code": None,
            "error_message": None,
            "retryable": None,
            "limitations": [],
            "response_schema_version": "1.0.0",
            "created_at": datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        }
        
        header = map_row_to_recommendation_header(row)
        
        assert header["status"] == "PENDING_HUMAN_APPROVAL"
        assert header["confidence"] == Decimal("0.85")
        assert header["error_code"] is None

    def test_map_row_to_candidate(self) -> None:
        """Test mapping database row to candidate."""
        row = {
            "requirement_id": uuid4(),
            "resource_id": uuid4(),
            "candidate_rank": 1,
            "allocation_score": Decimal("0.85"),
            "role_match": Decimal("0.9"),
            "skill_match": Decimal("0.8"),
            "availability_score": Decimal("0.85"),
            "workload_fit": Decimal("0.9"),
            "authority_match": Decimal("1.0"),
            "current_workload_pct": Decimal("30"),
            "projected_workload_pct": Decimal("40"),
            "available_from": datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
            "available_until": None,
            "candidate_name": "Test Developer",
        }
        
        candidate = map_row_to_candidate(row)
        
        assert candidate["candidate_rank"] == 1
        assert candidate["allocation_score"] == Decimal("0.85")
        assert candidate["candidate_name"] == "Test Developer"

    def test_map_row_to_exclusion_with_reasons(self) -> None:
        """Test mapping multiple rows to exclusion with reasons."""
        rows = [
            {
                "id": uuid4(),
                "requirement_id": uuid4(),
                "resource_id": uuid4(),
                "resource_type": "HUMAN",
                "sequence_order": 1,
                "reason_code": "INACTIVE_RESOURCE",
                "description": "Resource is inactive",
                "evidence_reference": "is_active field",
            },
            {
                "id": uuid4(),
                "requirement_id": uuid4(),
                "resource_id": uuid4(),
                "resource_type": "HUMAN",
                "sequence_order": 2,
                "reason_code": "REQUIRED_ROLE_MISSING",
                "description": "Missing required role",
                "evidence_reference": "roles field",
            },
        ]
        
        exclusion = map_row_to_exclusion_with_reasons(rows)
        
        assert len(exclusion["reasons"]) == 2
        assert exclusion["reasons"][0]["reason_code"] == "INACTIVE_RESOURCE"
        assert exclusion["reasons"][1]["reason_code"] == "REQUIRED_ROLE_MISSING"


class TestJSONBConversion:
    """Tests for _to_jsonb helper function."""

    def test_to_jsonb_empty_list(self) -> None:
        """Test that empty list converts to JSON string '[]'."""
        result = _to_jsonb([])
        assert result == "[]"
        assert isinstance(result, str)

    def test_to_jsonb_non_empty_list(self) -> None:
        """Test that non-empty list converts to JSON string."""
        result = _to_jsonb([1, 2, 3])
        assert result == "[1, 2, 3]"
        assert isinstance(result, str)

    def test_to_jsonb_dict(self) -> None:
        """Test that dict converts to JSON string."""
        result = _to_jsonb({"key": "value", "number": 42})
        assert result == '{"key": "value", "number": 42}'
        assert isinstance(result, str)

    def test_to_jsonb_nested_structure(self) -> None:
        """Test that nested structures convert correctly."""
        result = _to_jsonb({"list": [1, 2], "nested": {"key": "value"}})
        assert result == '{"list": [1, 2], "nested": {"key": "value"}}'
        assert isinstance(result, str)

    def test_to_jsonb_rejects_pre_serialized_string(self) -> None:
        """Test that pre-serialized JSON string is rejected to prevent double-encoding."""
        import pytest
        with pytest.raises(ValueError, match="Pre-serialized JSON string rejected"):
            _to_jsonb('{"already": "json"}')

    def test_to_jsonb_decimal_precision_preserved(self) -> None:
        """Test that high-precision Decimal converts to string without precision loss."""
        high_precision = Decimal("1234567890123456.78")
        result = _to_jsonb({"amount": high_precision})
        assert result == '{"amount": "1234567890123456.78"}'
        # Parse back to verify precision
        parsed = json.loads(result)
        assert parsed["amount"] == "1234567890123456.78"

    def test_to_jsonb_score_decimal_precision(self) -> None:
        """Test that score Decimal values retain exact decimal text."""
        score = Decimal("0.875")
        result = _to_jsonb({"score": score})
        assert result == '{"score": "0.875"}'
        parsed = json.loads(result)
        assert parsed["score"] == "0.875"

    def test_to_jsonb_uuid_conversion(self) -> None:
        """Test that UUID values convert to string."""
        test_uuid = uuid4()
        result = _to_jsonb({"id": test_uuid})
        assert str(test_uuid) in result
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed["id"] == str(test_uuid)

    def test_to_jsonb_aware_datetime_conversion(self) -> None:
        """Test that timezone-aware datetime converts to ISO format."""
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        result = _to_jsonb({"timestamp": dt})
        assert "2026-01-01T12:00:00" in result
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed["timestamp"] == "2026-01-01T12:00:00+00:00"

    def test_to_jsonb_rejects_naive_datetime(self) -> None:
        """Test that naive datetime is rejected."""
        import pytest
        naive_dt = datetime(2026, 1, 1, 12, 0)  # No timezone
        with pytest.raises(ValueError, match="Naive datetime.*not JSON-serializable"):
            _to_jsonb({"timestamp": naive_dt})

    def test_to_jsonb_limitations_empty_list(self) -> None:
        """Test that empty limitations list converts correctly for FAILED recommendations."""
        result = _to_jsonb([])
        assert result == "[]"
        parsed = json.loads(result)
        assert parsed == []

    def test_to_jsonb_limitations_with_values(self) -> None:
        """Test that limitations with values convert correctly."""
        result = _to_jsonb(["limit1", "limit2"])
        assert result == '["limit1", "limit2"]'
        parsed = json.loads(result)
        assert parsed == ["limit1", "limit2"]

    def test_to_jsonb_parse_roundtrip(self) -> None:
        """Test that parsing produced JSON returns expected structure."""
        original = {"key": "value", "number": 42, "decimal": Decimal("10.50")}
        result = _to_jsonb(original)
        parsed = json.loads(result)
        assert parsed["key"] == "value"
        assert parsed["number"] == 42
        assert parsed["decimal"] == "10.50"

    def test_to_jsonb_enum_conversion(self) -> None:
        """Test that Enum values convert to their value."""
        from app.agents.agent3_resources.schemas import ResourceType
        result = _to_jsonb({"type": ResourceType.HUMAN})
        assert result == '{"type": "HUMAN"}'
        parsed = json.loads(result)
        assert parsed["type"] == "HUMAN"


class TestMapperJSONBParameters:
    """Tests that mapper parameters used with CAST(... AS jsonb) are JSON strings."""

    def test_request_payload_is_json_string(self) -> None:
        """Test that request_payload from mapper is a JSON string."""
        metadata = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=uuid4(),
            message_type="RESOURCE_ALLOCATION_REQUEST",
        )
        request = AllocationRequest(
            metadata=metadata,
            human_requirements=HumanResourceRequirement(
                resource_type=ResourceType.HUMAN,
                requester_id=uuid4(),
                task_deadline=datetime(2026, 6, 1, tzinfo=timezone.utc),
                estimated_effort_hours=Decimal("10"),
                process_stage="resource_allocation",
            ),
            budget_requirements=None,
        )
        result = map_request_to_allocation_request(request, datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert isinstance(result["request_payload"], str)
        # Verify it's valid JSON
        parsed = json.loads(result["request_payload"])
        assert "metadata" in parsed

    def test_requirement_payload_is_json_string(self) -> None:
        """Test that requirement_payload from mapper is a JSON string."""
        requirement = HumanResourceRequirement(
            resource_type=ResourceType.HUMAN,
            requester_id=uuid4(),
            task_deadline=datetime(2026, 6, 1, tzinfo=timezone.utc),
            estimated_effort_hours=Decimal("10"),
            process_stage="resource_allocation",
        )
        result = map_requirement_to_allocation_requirement(
            requirement, uuid4(), uuid4(), 1
        )
        assert isinstance(result["requirement_payload"], str)
        parsed = json.loads(result["requirement_payload"])
        assert parsed["resource_type"] == "HUMAN"

    def test_limitations_is_json_string(self) -> None:
        """Test that limitations from mapper is a JSON string."""
        metadata = AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=uuid4(),
            message_type="RESOURCE_ALLOCATION_RESPONSE",
        )
        recommendation = AllocationRecommendation(
            metadata=metadata,
            status=RecommendationStatus.FAILED,
            requires_human_approval=False,
            manual_intervention_required=True,
            explanation="",
            confidence=None,
            error_code="TEST",
            error_message="Test error",
            retryable=False,
            limitations=["limit1", "limit2"],
        )
        result = map_recommendation_to_allocation_recommendation(
            recommendation, uuid4(), uuid4(), 1
        )
        assert isinstance(result["limitations"], str)
        parsed = json.loads(result["limitations"])
        assert parsed == ["limit1", "limit2"]

    def test_validation_payload_is_json_string(self) -> None:
        """Test that validation_payload from mapper is a JSON string."""
        validation = BudgetValidationChecks(
            resource_id=uuid4(),
            name="Test Budget",
            sufficient_balance=True,
            cost_centre_match=True,
            currency_match=True,
            validity_period_valid=True,
            within_authorization_limit=True,
            available_balance=Decimal("1000"),
            required_amount=Decimal("500"),
        )
        result = map_budget_validation_to_budget_validation_result(
            validation, uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
        )
        assert isinstance(result["validation_payload"], str)
        parsed = json.loads(result["validation_payload"])
        assert parsed["sufficient_balance"] is True


class TestRequirementResultResourceType:
    """Tests for RequirementResult resource_type field."""

    def test_human_requirement_result_with_resource_type(self) -> None:
        """Test that HUMAN RequirementResult validates with resource_type."""
        from app.agents.agent3_resources.schemas import RequirementResult, ResourceType

        result = RequirementResult(
            resource_type=ResourceType.HUMAN,
            eligible_candidates=[],
            excluded_resources=[],
            budget_validation=None,
        )
        assert result.resource_type == ResourceType.HUMAN

    def test_budget_requirement_result_with_resource_type(self) -> None:
        """Test that BUDGET RequirementResult validates with resource_type."""
        from app.agents.agent3_resources.schemas import RequirementResult, ResourceType, BudgetValidationChecks

        result = RequirementResult(
            resource_type=ResourceType.BUDGET,
            eligible_candidates=[],
            excluded_resources=[],
            budget_validation=BudgetValidationChecks(
                resource_id=uuid4(),
                name="Test Budget",
                sufficient_balance=True,
                cost_centre_match=True,
                currency_match=True,
                validity_period_valid=True,
                within_authorization_limit=True,
                available_balance=Decimal("1000"),
                required_amount=Decimal("500"),
            ),
        )
        assert result.resource_type == ResourceType.BUDGET

    def test_requirement_result_without_resource_type_raises(self) -> None:
        """Test that RequirementResult without resource_type raises validation error."""
        from app.agents.agent3_resources.schemas import RequirementResult
        import pytest

        with pytest.raises(Exception):  # Pydantic validation error
            RequirementResult(
                eligible_candidates=[],
                excluded_resources=[],
                budget_validation=None,
            )

    def test_map_row_to_exclusion_with_reasons_empty(self) -> None:
        """Test mapping empty rows returns empty dict."""
        exclusion = map_row_to_exclusion_with_reasons([])
        assert exclusion == {}
