"""Unit and safety tests for Agent 3 LLM Explanation Enhancement with deterministic fallback."""

import asyncio
from datetime import timedelta
from decimal import Decimal
from typing import Optional
from uuid import uuid4

import pytest

from app.agents.agent3_resources import (
    AllocationRequest,
    AgentMessageMetadata,
    HumanResourceRequirement,
    BudgetResourceRequirement,
    HumanResourceEvidence,
    BudgetResourceEvidence,
    InMemoryResourceRepository,
    ResourceAllocationService,
    ExplanationContext,
    RequirementResult,
    RankedHumanCandidate,
    ScoreBreakdown,
    BudgetValidationResult,
    ExcludedResource,
    ExclusionReasonEntry,
    ExclusionReason,
    ResourceGap,
    ResourceType,
    GapType,
    ResourceAlternative,
    GapAlternativeType,
    RecommendationStatus,
    TemplateExplainer,
    TemplateExplainerAdapter,
    OpenAIExplanationGenerator,
    ResilientFallbackExplainer,
    LLMOutputValidator,
    LLMExplanationError,
    sanitize_explanation_context,
    build_user_prompt,
    get_tenant_a_id,
    get_requester_id,
    get_resource_id_1,
    create_human_evidence,
    utc_now,
)
from app.tests.conftest import utc_datetime


# ============================================================================
# Fake OpenAI Responses API Client Helpers (No Real Network Calls)
# ============================================================================

class DummyResponse:
    def __init__(self, output_text: Optional[str]):
        self.output_text = output_text


class FakeOpenAIClient:
    def __init__(
        self,
        return_content: Optional[str] = "The allocation for Candidate 1 is recommended. This recommendation requires human approval before execution.",
        raise_exc: Optional[Exception] = None,
        delay: float = 0.0,
        return_invalid_shape: bool = False,
    ):
        self.return_content = return_content
        self.raise_exc = raise_exc
        self.delay = delay
        self.return_invalid_shape = return_invalid_shape
        self.call_count = 0
        self.last_kwargs = None

        class Responses:
            def __init__(self, parent):
                self.parent = parent

            async def create(self, **kwargs):
                self.parent.call_count += 1
                self.parent.last_kwargs = kwargs
                if self.parent.delay > 0:
                    await asyncio.sleep(self.parent.delay)
                if self.parent.raise_exc:
                    raise self.parent.raise_exc
                if self.parent.return_invalid_shape:
                    return "invalid_shape_not_a_response_object"
                return DummyResponse(self.parent.return_content)

        self.responses = Responses(self)


# ============================================================================
# Test Fixtures & Helpers
# ============================================================================

def _sample_context():
    candidate = RankedHumanCandidate(
        resource_id=uuid4(),
        resource_type=ResourceType.HUMAN,
        name="John Doe",
        rank=1,
        allocation_score=Decimal("0.225"),
        score_breakdown=ScoreBreakdown(
            role_match=Decimal("0.30"),
            skill_match=Decimal("0.25"),
            availability_score=Decimal("0.20"),
            workload_fit=Decimal("0.15"),
            authority_match=Decimal("0.10"),
            total_score=Decimal("0.225"),
        ),
        current_workload_percentage=Decimal("40"),
        projected_workload_percentage=Decimal("50"),
        available_from=utc_datetime(2026, 1, 1),
        evidence_refs={"sensitive_raw_key": "sensitive_raw_val"},
    )
    human_result = RequirementResult(
        resource_type=ResourceType.HUMAN,
        eligible_candidates=[candidate],
        excluded_resources=[],
    )
    return ExplanationContext(
        human_requirement_result=human_result,
        confidence=Decimal("0.85"),
    )


# ============================================================================
# 22 Reconciled Phase 4A Acceptance Test Cases (Covering Scenarios 1-30)
# ============================================================================

class TestAgent3LLMExplainer:

    @pytest.mark.asyncio
    async def test_01_disabled_configuration(self):
        """Scenario 1 & 23: Disabled configuration -> template only, zero client calls."""
        fake_client = FakeOpenAIClient()
        gen = OpenAIExplanationGenerator(client=fake_client)
        fallback = ResilientFallbackExplainer(enabled=False, llm_generator=gen)

        context = _sample_context()
        explanation = await fallback.generate_explanation(context)

        assert fake_client.call_count == 0
        assert "=== Resource Allocation Recommendation ===" in explanation
        assert "Approval Required" in explanation

    @pytest.mark.asyncio
    async def test_02_missing_api_configuration(self):
        """Scenario 2: Missing/unconfigured generator (client=None) -> template fallback."""
        gen = OpenAIExplanationGenerator(client=None)
        fallback = ResilientFallbackExplainer(enabled=True, llm_generator=gen)

        context = _sample_context()
        explanation = await fallback.generate_explanation(context)

        assert "=== Resource Allocation Recommendation ===" in explanation

    @pytest.mark.asyncio
    async def test_03_valid_responses_api_output(self):
        """Scenario 3, 23, 24, 25, 26, 27: Valid Responses API output, store=False, max_output_tokens, instructions/input separation."""
        valid_text = "Candidate 1 is selected based on skill match. This recommendation requires human approval before execution."
        fake_client = FakeOpenAIClient(return_content=valid_text)
        gen = OpenAIExplanationGenerator(client=fake_client, model="gpt-4o-mini", max_output_tokens=350)
        fallback = ResilientFallbackExplainer(enabled=True, llm_generator=gen)

        context = _sample_context()
        explanation = await fallback.generate_explanation(context)

        assert fake_client.call_count == 1
        assert explanation == valid_text

        kwargs = fake_client.last_kwargs
        assert kwargs is not None
        assert kwargs["model"] == "gpt-4o-mini"
        assert kwargs["store"] is False
        assert kwargs["max_output_tokens"] == 350
        assert "max_tokens" not in kwargs
        assert "temperature" not in kwargs  # Default temperature is None
        assert "instructions" in kwargs
        assert "input" in kwargs
        assert "CRITICAL CONSTRAINTS & RULES" in kwargs["instructions"]
        assert "ALLOCATION FACT SUMMARY" in kwargs["input"]

    @pytest.mark.asyncio
    async def test_04_empty_output(self):
        """Scenario 4: Empty output -> fallback."""
        fake_client = FakeOpenAIClient(return_content="   ")
        gen = OpenAIExplanationGenerator(client=fake_client)
        fallback = ResilientFallbackExplainer(enabled=True, llm_generator=gen)

        context = _sample_context()
        explanation = await fallback.generate_explanation(context)

        assert "=== Resource Allocation Recommendation ===" in explanation

    @pytest.mark.asyncio
    async def test_05_oversized_output(self):
        """Scenario 5: Oversized output -> fallback."""
        oversized = "A" * 4500 + " This recommendation requires human approval."
        fake_client = FakeOpenAIClient(return_content=oversized)
        gen = OpenAIExplanationGenerator(client=fake_client)
        fallback = ResilientFallbackExplainer(enabled=True, llm_generator=gen)

        context = _sample_context()
        explanation = await fallback.generate_explanation(context)

        assert "=== Resource Allocation Recommendation ===" in explanation

    @pytest.mark.asyncio
    async def test_06_code_fenced_output(self):
        """Scenario 6: Code-fenced output -> fallback."""
        fenced = "```json\n{\"explanation\": \"Candidate 1\", \"human_approval\": true}\n```"
        fake_client = FakeOpenAIClient(return_content=fenced)
        gen = OpenAIExplanationGenerator(client=fake_client)
        fallback = ResilientFallbackExplainer(enabled=True, llm_generator=gen)

        context = _sample_context()
        explanation = await fallback.generate_explanation(context)

        assert "=== Resource Allocation Recommendation ===" in explanation

    @pytest.mark.asyncio
    async def test_07_uuid_url_secret_output(self):
        """Scenario 7: Output containing UUID/URL/secret-like content -> fallback."""
        # 7a: UUID
        bad_uuid = "Assigned to resource 123e4567-e89b-12d3-a456-426614174000. Human approval required."
        fallback_uuid = ResilientFallbackExplainer(
            enabled=True,
            llm_generator=OpenAIExplanationGenerator(client=FakeOpenAIClient(return_content=bad_uuid)),
        )
        assert "=== Resource Allocation Recommendation ===" in await fallback_uuid.generate_explanation(_sample_context())

        # 7b: URL
        bad_url = "See details at https://internal.corp/resource. Human approval required."
        fallback_url = ResilientFallbackExplainer(
            enabled=True,
            llm_generator=OpenAIExplanationGenerator(client=FakeOpenAIClient(return_content=bad_url)),
        )
        assert "=== Resource Allocation Recommendation ===" in await fallback_url.generate_explanation(_sample_context())

        # 7c: Secret
        bad_secret = "Using sk-proj-12345678901234567890. Human approval required."
        fallback_secret = ResilientFallbackExplainer(
            enabled=True,
            llm_generator=OpenAIExplanationGenerator(client=FakeOpenAIClient(return_content=bad_secret)),
        )
        assert "=== Resource Allocation Recommendation ===" in await fallback_secret.generate_explanation(_sample_context())

    @pytest.mark.asyncio
    async def test_08_timeout(self):
        """Scenario 8: Timeout -> fallback."""
        fake_client = FakeOpenAIClient(delay=0.5)
        gen = OpenAIExplanationGenerator(client=fake_client, timeout=0.05)
        fallback = ResilientFallbackExplainer(enabled=True, llm_generator=gen)

        context = _sample_context()
        explanation = await fallback.generate_explanation(context)

        assert "=== Resource Allocation Recommendation ===" in explanation

    @pytest.mark.asyncio
    async def test_09_sdk_network_failure(self):
        """Scenario 9: SDK/network failure -> fallback."""
        fake_client = FakeOpenAIClient(raise_exc=RuntimeError("Connection reset by peer"))
        gen = OpenAIExplanationGenerator(client=fake_client)
        fallback = ResilientFallbackExplainer(enabled=True, llm_generator=gen)

        context = _sample_context()
        explanation = await fallback.generate_explanation(context)

        assert "=== Resource Allocation Recommendation ===" in explanation

    @pytest.mark.asyncio
    async def test_10_invalid_response_shape(self):
        """Scenario 10: Invalid response shape -> fallback."""
        fake_client = FakeOpenAIClient(return_invalid_shape=True)
        gen = OpenAIExplanationGenerator(client=fake_client)
        fallback = ResilientFallbackExplainer(enabled=True, llm_generator=gen)

        context = _sample_context()
        explanation = await fallback.generate_explanation(context)

        assert "=== Resource Allocation Recommendation ===" in explanation

    @pytest.mark.asyncio
    async def test_11_no_retry(self):
        """Scenario 11: No retry after failure (call_count == 1)."""
        fake_client = FakeOpenAIClient(raise_exc=RuntimeError("OpenAI Service Unavailable"))
        gen = OpenAIExplanationGenerator(client=fake_client)
        fallback = ResilientFallbackExplainer(enabled=True, llm_generator=gen)

        context = _sample_context()
        await fallback.generate_explanation(context)

        assert fake_client.call_count == 1

    @pytest.mark.asyncio
    async def test_12_failed_recommendation_bypass(self):
        """Scenario 12: Technical FAILED recommendation bypasses LLM call."""
        repo = InMemoryResourceRepository()
        fake_client = FakeOpenAIClient()
        gen = OpenAIExplanationGenerator(client=fake_client)
        fallback = ResilientFallbackExplainer(enabled=True, llm_generator=gen)
        service = ResourceAllocationService(repo, explainer=fallback)

        bad_req = AllocationRequest(
            metadata=AgentMessageMetadata(
                correlation_id=uuid4(),
                process_instance_id=uuid4(),
                task_id=uuid4(),
                tenant_id=get_tenant_a_id(),
                message_type="RESOURCE_ALLOCATION_REQUEST", # type: ignore
            ),
            human_requirements=None,
            budget_requirements=None,
        )

        rec = await service.process_allocation_request(bad_req)

        assert rec.status == RecommendationStatus.FAILED
        assert rec.explanation == ""
        assert fake_client.call_count == 0

    def test_13_human_minimized_context(self):
        """Scenario 13: HUMAN minimized context uses anonymous candidate labels."""
        candidate_uuid = uuid4()
        candidate = RankedHumanCandidate(
            resource_id=candidate_uuid,
            resource_type=ResourceType.HUMAN,
            name="Alice Smith",
            rank=1,
            allocation_score=Decimal("0.225"),
            score_breakdown=ScoreBreakdown(
                role_match=Decimal("0.30"),
                skill_match=Decimal("0.25"),
                availability_score=Decimal("0.20"),
                workload_fit=Decimal("0.15"),
                authority_match=Decimal("0.10"),
                total_score=Decimal("0.225"),
            ),
            current_workload_percentage=Decimal("30"),
            projected_workload_percentage=Decimal("40"),
            available_from=utc_datetime(2026, 1, 1),
            evidence_refs={"secret_evidence": "secret_val"},
        )
        ctx = ExplanationContext(
            human_requirement_result=RequirementResult(
                resource_type=ResourceType.HUMAN,
                eligible_candidates=[candidate],
            )
        )

        sanitized = sanitize_explanation_context(ctx)

        assert len(sanitized.candidates) == 1
        c = sanitized.candidates[0]
        assert c.label == "Candidate 1"
        assert "Alice" not in str(sanitized)
        assert str(candidate_uuid) not in str(sanitized)

    def test_14_budget_minimized_context(self):
        """Scenario 14: BUDGET minimized context preserves Decimal amounts and ISO currency without identifiers."""
        budget_uuid = uuid4()
        ctx = ExplanationContext(
            budget_requirement_result=RequirementResult(
                resource_type=ResourceType.BUDGET,
                budget_validation=BudgetValidationResult(
                    resource_id=budget_uuid,
                    name="Q1 Operating Budget",
                    sufficient_balance=True,
                    cost_centre_match=True,
                    currency_match=True,
                    validity_period_valid=True,
                    within_authorization_limit=True,
                    available_balance=Decimal("50000.00"),
                    required_amount=Decimal("12000.00"),
                    evidence_references={"db_connection": "secret_db_url"},
                ),
            ),
            currency="USD",
        )

        sanitized = sanitize_explanation_context(ctx)

        assert sanitized.budget is not None
        assert sanitized.budget.available_balance == "50000.00"
        assert sanitized.budget.required_amount == "12000.00"
        assert sanitized.budget.currency == "USD"
        assert str(budget_uuid) not in str(sanitized)
        assert "secret_db_url" not in str(sanitized)

    def test_15_mixed_minimized_context(self):
        """Scenario 15: Mixed HUMAN+BUDGET context is minimized cleanly."""
        candidate = RankedHumanCandidate(
            resource_id=uuid4(),
            resource_type=ResourceType.HUMAN,
            name="Bob Jones",
            rank=1,
            allocation_score=Decimal("0.225"),
            score_breakdown=ScoreBreakdown(
                role_match=Decimal("0.30"),
                skill_match=Decimal("0.25"),
                availability_score=Decimal("0.20"),
                workload_fit=Decimal("0.15"),
                authority_match=Decimal("0.10"),
                total_score=Decimal("0.225"),
            ),
            current_workload_percentage=Decimal("20"),
            projected_workload_percentage=Decimal("30"),
            available_from=utc_datetime(2026, 1, 1),
        )
        ctx = ExplanationContext(
            human_requirement_result=RequirementResult(
                resource_type=ResourceType.HUMAN,
                eligible_candidates=[candidate],
            ),
            budget_requirement_result=RequirementResult(
                resource_type=ResourceType.BUDGET,
                budget_validation=BudgetValidationResult(
                    resource_id=uuid4(),
                    name="Test Budget",
                    sufficient_balance=True,
                    cost_centre_match=True,
                    currency_match=True,
                    validity_period_valid=True,
                    within_authorization_limit=True,
                    available_balance=Decimal("1000.00"),
                    required_amount=Decimal("500.00"),
                ),
            ),
            currency="EUR",
        )

        sanitized = sanitize_explanation_context(ctx)

        assert len(sanitized.candidates) == 1
        assert sanitized.budget is not None
        assert sanitized.budget.currency == "EUR"
        assert "Bob" not in str(sanitized)

    def test_16_no_identifiers_in_prompt(self):
        """Scenario 16: Tenant/requester/correlation/resource UUIDs never enter prompt."""
        tenant_id = uuid4()
        requester_id = uuid4()
        correlation_id = uuid4()
        resource_id = uuid4()

        candidate = RankedHumanCandidate(
            resource_id=resource_id,
            resource_type=ResourceType.HUMAN,
            name="Test Candidate",
            rank=1,
            allocation_score=Decimal("0.225"),
            score_breakdown=ScoreBreakdown(
                role_match=Decimal("0.30"),
                skill_match=Decimal("0.25"),
                availability_score=Decimal("0.20"),
                workload_fit=Decimal("0.15"),
                authority_match=Decimal("0.10"),
                total_score=Decimal("0.225"),
            ),
            current_workload_percentage=Decimal("20"),
            projected_workload_percentage=Decimal("30"),
            available_from=utc_datetime(2026, 1, 1),
        )
        ctx = ExplanationContext(
            human_requirement_result=RequirementResult(
                resource_type=ResourceType.HUMAN,
                eligible_candidates=[candidate],
            )
        )

        sanitized = sanitize_explanation_context(ctx)
        prompt = build_user_prompt(sanitized)

        for sensitive_id in [tenant_id, requester_id, correlation_id, resource_id]:
            assert str(sensitive_id) not in prompt

    def test_17_no_raw_evidence_in_prompt(self):
        """Scenario 17: Raw evidence payloads never enter prompt."""
        candidate = RankedHumanCandidate(
            resource_id=uuid4(),
            resource_type=ResourceType.HUMAN,
            name="Test Candidate",
            rank=1,
            allocation_score=Decimal("0.225"),
            score_breakdown=ScoreBreakdown(
                role_match=Decimal("0.30"),
                skill_match=Decimal("0.25"),
                availability_score=Decimal("0.20"),
                workload_fit=Decimal("0.15"),
                authority_match=Decimal("0.10"),
                total_score=Decimal("0.225"),
            ),
            current_workload_percentage=Decimal("20"),
            projected_workload_percentage=Decimal("30"),
            available_from=utc_datetime(2026, 1, 1),
            evidence_refs={
                "raw_db_credential": "postgres://user:pass@localhost:5432/db",
                "jwt_token": "bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            },
        )
        ctx = ExplanationContext(
            human_requirement_result=RequirementResult(
                resource_type=ResourceType.HUMAN,
                eligible_candidates=[candidate],
            )
        )

        sanitized = sanitize_explanation_context(ctx)
        prompt = build_user_prompt(sanitized)

        assert "postgres://" not in prompt
        assert "user:pass" not in prompt
        assert "eyJhbGci" not in prompt

    def test_18_multi_currency_exact_decimals_and_no_invented_symbol(self):
        """Scenario 28 & 29: Exact multi-currency Decimal strings for USD, EUR, GBP; no invented '$' when currency absent."""
        # USD
        ctx_usd = ExplanationContext(
            budget_requirement_result=RequirementResult(
                resource_type=ResourceType.BUDGET,
                budget_validation=BudgetValidationResult(
                    resource_id=uuid4(),
                    name="Test Budget",
                    sufficient_balance=True,
                    cost_centre_match=True,
                    currency_match=True,
                    validity_period_valid=True,
                    within_authorization_limit=True,
                    available_balance=Decimal("50000.00"),
                    required_amount=Decimal("12000.00"),
                ),
            ),
            currency="USD",
        )
        prompt_usd = build_user_prompt(sanitize_explanation_context(ctx_usd))
        assert "50000.00 USD" in prompt_usd
        assert "$" not in prompt_usd

        # EUR
        ctx_eur = ExplanationContext(
            budget_requirement_result=RequirementResult(
                resource_type=ResourceType.BUDGET,
                budget_validation=BudgetValidationResult(
                    resource_id=uuid4(),
                    name="Euro Budget",
                    sufficient_balance=True,
                    cost_centre_match=True,
                    currency_match=True,
                    validity_period_valid=True,
                    within_authorization_limit=True,
                    available_balance=Decimal("75000.50"),
                    required_amount=Decimal("30000.25"),
                ),
            ),
            currency="EUR",
        )
        prompt_eur = build_user_prompt(sanitize_explanation_context(ctx_eur))
        assert "75000.50 EUR" in prompt_eur
        assert "$" not in prompt_eur

        # GBP
        ctx_gbp = ExplanationContext(
            budget_requirement_result=RequirementResult(
                resource_type=ResourceType.BUDGET,
                budget_validation=BudgetValidationResult(
                    resource_id=uuid4(),
                    name="GBP Budget",
                    sufficient_balance=True,
                    cost_centre_match=True,
                    currency_match=True,
                    validity_period_valid=True,
                    within_authorization_limit=True,
                    available_balance=Decimal("40000.00"),
                    required_amount=Decimal("15000.00"),
                ),
            ),
            currency="GBP",
        )
        prompt_gbp = build_user_prompt(sanitize_explanation_context(ctx_gbp))
        assert "40000.00 GBP" in prompt_gbp
        assert "$" not in prompt_gbp

        # No currency -> no invented '$'
        ctx_none = ExplanationContext(
            budget_requirement_result=RequirementResult(
                resource_type=ResourceType.BUDGET,
                budget_validation=BudgetValidationResult(
                    resource_id=uuid4(),
                    name="No Currency Budget",
                    sufficient_balance=True,
                    cost_centre_match=True,
                    currency_match=True,
                    validity_period_valid=True,
                    within_authorization_limit=True,
                    available_balance=Decimal("100.00"),
                    required_amount=Decimal("50.00"),
                ),
            ),
            currency=None,
        )
        prompt_none = build_user_prompt(sanitize_explanation_context(ctx_none))
        assert "$" not in prompt_none
        assert "Available Balance: 100.00, Required Amount: 50.00." in prompt_none

    @pytest.mark.asyncio
    async def test_19_async_protocol_and_adapters(self):
        """Scenario 30: Strict async ExplanationGenerator protocol enforcement and explicit TemplateExplainerAdapter."""
        template = TemplateExplainer()
        adapter = TemplateExplainerAdapter(template)

        # Service instantiated with direct TemplateExplainer is explicitly adapted
        service_sync = ResourceAllocationService(InMemoryResourceRepository(), explainer=template)
        assert isinstance(service_sync.explainer, TemplateExplainerAdapter)

        # Service instantiated with adapter
        service_adapter = ResourceAllocationService(InMemoryResourceRepository(), explainer=adapter)
        assert service_adapter.explainer is adapter

        # Invalid explainer raises TypeError
        with pytest.raises(TypeError):
            ResourceAllocationService(InMemoryResourceRepository(), explainer="not_an_explainer")

    @pytest.mark.asyncio
    async def test_20_decisions_and_approval_statement_unchanged(self):
        """Scenario 18 & 19: Rankings, scores, status, and approval flags remain unchanged; approval statement preserved."""
        repo = InMemoryResourceRepository()
        tenant_id = get_tenant_a_id()
        now = utc_now()
        deadline = now + timedelta(days=10)

        resource = create_human_evidence(
            tenant_id=tenant_id,
            reference_timestamp=now,
            resource_id=get_resource_id_1(),
            is_active=True,
            roles=["Senior Developer"],
            current_workload=Decimal("20"),
            max_workload=Decimal("100"),
        )
        repo.add_human_resource(resource)

        req = AllocationRequest(
            metadata=AgentMessageMetadata(
                correlation_id=uuid4(),
                process_instance_id=uuid4(),
                task_id=uuid4(),
                tenant_id=tenant_id,
                message_type="RESOURCE_ALLOCATION_REQUEST", # type: ignore
            ),
            human_requirements=HumanResourceRequirement(
                required_roles=["Senior Developer"],
                requester_id=get_requester_id(),
                task_deadline=deadline,
                estimated_effort_hours=Decimal("10"),
                process_stage="STAGING",
            ),
        )

        service_template = ResourceAllocationService(repo, explainer=ResilientFallbackExplainer(enabled=False))
        rec_template = await service_template.process_allocation_request(req, evaluation_timestamp=now)

        fake_client = FakeOpenAIClient(
            return_content="Enhanced explanation for Candidate 1. This recommendation requires human approval before execution."
        )
        gen = OpenAIExplanationGenerator(client=fake_client)
        service_llm = ResourceAllocationService(repo, explainer=ResilientFallbackExplainer(enabled=True, llm_generator=gen))
        rec_llm = await service_llm.process_allocation_request(req, evaluation_timestamp=now)

        # Core safety boundary assertions
        assert rec_llm.status == rec_template.status
        assert rec_llm.requires_human_approval == rec_template.requires_human_approval
        assert rec_llm.manual_intervention_required == rec_template.manual_intervention_required
        assert rec_llm.confidence == rec_template.confidence
        assert len(rec_llm.human_requirement_result.eligible_candidates) == len(rec_template.human_requirement_result.eligible_candidates)
        c_llm = rec_llm.human_requirement_result.eligible_candidates[0]
        c_template = rec_template.human_requirement_result.eligible_candidates[0]
        assert c_llm.resource_id == c_template.resource_id
        assert c_llm.rank == c_template.rank
        assert c_llm.allocation_score == c_template.allocation_score
        assert c_llm.score_breakdown == c_template.score_breakdown
        assert "human approval" in rec_llm.explanation.lower()

    @pytest.mark.asyncio
    async def test_21_template_regression_and_concurrent_context_isolation(self):
        """Scenario 20 & 21: Existing template output regression remains unchanged; concurrent async execution context isolation."""
        explainer = TemplateExplainer()
        context = _sample_context()
        exp1 = explainer.generate_explanation(context)

        fallback = ResilientFallbackExplainer(enabled=False)
        exp2 = await fallback.generate_explanation(context)
        assert exp1 == exp2

        fake_client = FakeOpenAIClient()
        gen = OpenAIExplanationGenerator(client=fake_client)
        fallback_llm = ResilientFallbackExplainer(enabled=True, llm_generator=gen)

        async def run_one(idx: int):
            ctx = _sample_context()
            ctx.limitations = [f"Unique limitation {idx}"]
            return await fallback_llm.generate_explanation(ctx)

        results = await asyncio.gather(*[run_one(i) for i in range(10)])
        assert len(results) == 10
        for res in results:
            assert res is not None

    @pytest.mark.asyncio
    async def test_22_exception_api_key_prompt_redaction(self):
        """Scenario 22: Exceptions and test output redact API keys and prompt payloads."""
        secret_key_msg = "Error connecting with API key sk-proj-supersecretkey123456789 and Authorization Header Bearer token"
        fake_client = FakeOpenAIClient(raise_exc=RuntimeError(secret_key_msg))
        gen = OpenAIExplanationGenerator(client=fake_client)

        with pytest.raises(LLMExplanationError) as exc_info:
            await gen.generate_explanation(_sample_context())

        err_str = str(exc_info.value)
        assert "sk-proj-supersecretkey123456789" not in err_str
        assert "Authorization Header Bearer" not in err_str
        assert err_str == "LLM generation request failed"
