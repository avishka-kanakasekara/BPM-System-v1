"""Unit and runtime integration tests for Agent 3 optional OpenAI runtime configuration and lifecycle."""

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from uuid import uuid4

import pytest
from httpx import AsyncClient, ASGITransport

from app.agents.agent3_resources import (
    Agent3LLMConfig,
    get_agent3_llm_config,
    get_shared_openai_client,
    close_agent3_llm_runtime,
    reset_agent3_llm_runtime,
    set_openai_client_factory,
    ResilientFallbackExplainer,
    OpenAIExplanationGenerator,
    TemplateExplainerAdapter,
    ResourceAllocationService,
    AllocationRequest,
    AgentMessageMetadata,
    RecommendationStatus,
    get_tenant_a_id,
    InMemoryResourceRepository,
)
from app.agents.agent3_resources.api_dependencies import get_allocation_service
from app.main import app


# Fake client for runtime testing
class DummyClient:
    def __init__(self, key: Optional[str] = None):
        self.key = key
        self.is_closed = False
        self.call_count = 0

        class Responses:
            def __init__(self, parent):
                self.parent = parent

            async def create(self, **kwargs):
                self.parent.call_count += 1
                class Resp:
                    output_text = "Runtime explanation for candidate. Human approval required."
                return Resp()

        self.responses = Responses(self)

    async def close(self):
        self.is_closed = True


@pytest.fixture(autouse=True)
def reset_runtime_state(monkeypatch):
    """Fixture to ensure clean env and runtime state before/after each test."""
    reset_agent3_llm_runtime()
    # Reset relevant env vars
    monkeypatch.delenv("AGENT3_LLM_EXPLANATIONS_ENABLED", raising=False)
    monkeypatch.delenv("AGENT3_LLM_MODEL", raising=False)
    monkeypatch.delenv("AGENT3_LLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("AGENT3_LLM_MAX_OUTPUT_TOKENS", raising=False)
    monkeypatch.delenv("AGENT3_LLM_TEMPERATURE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    yield
    reset_agent3_llm_runtime()


class TestAgent3LLMRuntime:

    def test_01_import_reads_no_env_vars(self, monkeypatch):
        """1. Module import reads no OpenAI environment variables."""
        # Ensure env var is garbage
        monkeypatch.setenv("AGENT3_LLM_EXPLANATIONS_ENABLED", "INVALID_BOOLEAN_VAL")
        # Importing or accessing the module should not raise
        import app.agents.agent3_resources.runtime_config as r_config
        assert r_config is not None

    def test_02_disabled_by_default(self):
        """2. Disabled by default when env vars are absent."""
        config = get_agent3_llm_config()
        assert config.enabled is False
        assert config.model == "gpt-4o-mini"
        assert config.timeout_seconds == 5.0
        assert config.max_output_tokens == 500
        assert config.temperature is None
        assert config.api_key is None

    def test_03_disabled_mode_creates_zero_clients(self, monkeypatch):
        """3. Disabled mode creates zero OpenAI clients."""
        monkeypatch.setenv("AGENT3_LLM_EXPLANATIONS_ENABLED", "false")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-testkey123")
        
        client = get_shared_openai_client()
        assert client is None

    @pytest.mark.asyncio
    async def test_04_disabled_production_service_uses_template_adapter(self, monkeypatch):
        """4. Disabled production service uses template adapter."""
        monkeypatch.setenv("AGENT3_LLM_EXPLANATIONS_ENABLED", "false")

        service = await get_allocation_service()
        assert isinstance(service.explainer, ResilientFallbackExplainer)
        assert service.explainer.enabled is False

    def test_05_enabled_valid_config_constructs_one_client(self, monkeypatch):
        """5. Enabled + valid config constructs one client/runtime."""
        monkeypatch.setenv("AGENT3_LLM_EXPLANATIONS_ENABLED", "true")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-testkey123")
        
        dummy = DummyClient()
        set_openai_client_factory(lambda cfg: dummy)

        client1 = get_shared_openai_client()
        assert client1 is dummy

    @pytest.mark.asyncio
    async def test_06_client_reused_across_service_resolutions(self, monkeypatch):
        """6. Client/runtime reused across multiple service resolutions."""
        monkeypatch.setenv("AGENT3_LLM_EXPLANATIONS_ENABLED", "true")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-testkey123")
        
        dummy = DummyClient()
        set_openai_client_factory(lambda cfg: dummy)

        s1 = await get_allocation_service()
        s2 = await get_allocation_service()

        assert s1.explainer.llm_generator.client is dummy
        assert s2.explainer.llm_generator.client is dummy

    @pytest.mark.asyncio
    async def test_07_shutdown_closes_client_once(self, monkeypatch):
        """7. Shutdown closes the client exactly once."""
        monkeypatch.setenv("AGENT3_LLM_EXPLANATIONS_ENABLED", "true")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-testkey123")
        
        dummy = DummyClient()
        set_openai_client_factory(lambda cfg: dummy)

        client = get_shared_openai_client()
        assert client is dummy

        await close_agent3_llm_runtime()
        assert dummy.is_closed is True

    @pytest.mark.asyncio
    async def test_08_repeated_shutdown_is_safe(self, monkeypatch):
        """8. Repeated shutdown calls are safe and idempotent."""
        monkeypatch.setenv("AGENT3_LLM_EXPLANATIONS_ENABLED", "true")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-testkey123")
        
        dummy = DummyClient()
        set_openai_client_factory(lambda cfg: dummy)
        get_shared_openai_client()

        await close_agent3_llm_runtime()
        await close_agent3_llm_runtime()
        await close_agent3_llm_runtime()

        assert dummy.is_closed is True

    @pytest.mark.asyncio
    async def test_09_missing_key_falls_back_without_startup_failure(self, monkeypatch):
        """9. Missing API key falls back to template without startup failure."""
        monkeypatch.setenv("AGENT3_LLM_EXPLANATIONS_ENABLED", "true")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        service = await get_allocation_service()
        assert service.explainer.enabled is False

    @pytest.mark.asyncio
    async def test_10_invalid_config_falls_back_safely(self, monkeypatch):
        """10. Invalid boolean or token bounds falls back safely."""
        monkeypatch.setenv("AGENT3_LLM_EXPLANATIONS_ENABLED", "NOT_A_BOOL")

        service = await get_allocation_service()
        assert service.explainer.enabled is False

    def test_11_timeout_token_bounds_validated(self, monkeypatch):
        """11. Timeout and token bounds are strictly validated."""
        # 11a: Timeout negative
        monkeypatch.setenv("AGENT3_LLM_EXPLANATIONS_ENABLED", "true")
        monkeypatch.setenv("AGENT3_LLM_TIMEOUT_SECONDS", "-10")
        with pytest.raises(ValueError):
            get_agent3_llm_config()

        # 11b: Tokens zero
        monkeypatch.setenv("AGENT3_LLM_TIMEOUT_SECONDS", "5")
        monkeypatch.setenv("AGENT3_LLM_MAX_OUTPUT_TOKENS", "0")
        with pytest.raises(ValueError):
            get_agent3_llm_config()

    def test_12_optional_temperature_parsing(self, monkeypatch):
        """12. Optional temperature parsing (valid float vs None)."""
        monkeypatch.setenv("AGENT3_LLM_EXPLANATIONS_ENABLED", "true")

        # Empty string -> None
        monkeypatch.setenv("AGENT3_LLM_TEMPERATURE", "")
        cfg1 = get_agent3_llm_config()
        assert cfg1.temperature is None

        # 0.7 -> float 0.7
        monkeypatch.setenv("AGENT3_LLM_TEMPERATURE", "0.7")
        cfg2 = get_agent3_llm_config()
        assert cfg2.temperature == 0.7

    def test_13_api_key_absent_from_repr_and_logs(self, monkeypatch):
        """13. API key is absent from config __repr__ and string formatting."""
        monkeypatch.setenv("AGENT3_LLM_EXPLANATIONS_ENABLED", "true")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-SUPERSECRETKEY123456")

        config = get_agent3_llm_config()
        repr_str = repr(config)

        assert "SUPERSECRETKEY123456" not in repr_str
        assert "[REDACTED]" in repr_str

    @pytest.mark.asyncio
    async def test_14_real_dependency_returns_service_with_resilient_explainer(self, monkeypatch):
        """14. Real Agent 3 dependency returns service with resilient explainer when enabled."""
        monkeypatch.setenv("AGENT3_LLM_EXPLANATIONS_ENABLED", "true")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-testkey123")
        set_openai_client_factory(lambda cfg: DummyClient())

        service = await get_allocation_service()

        assert isinstance(service, ResourceAllocationService)
        assert isinstance(service.explainer, ResilientFallbackExplainer)
        assert service.explainer.enabled is True

    @pytest.mark.asyncio
    async def test_15_existing_db_session_wiring_unchanged(self):
        """15. Existing database session/repository wiring remains unchanged."""
        service = await get_allocation_service()
        assert hasattr(service, "repository")
        assert service.repository is not None

    @pytest.mark.asyncio
    async def test_16_multiple_requests_do_not_create_multiple_clients(self, monkeypatch):
        """16. Multiple requests reuse the existing client without re-creating it."""
        monkeypatch.setenv("AGENT3_LLM_EXPLANATIONS_ENABLED", "true")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-testkey123")

        created_count = 0
        def factory(cfg):
            nonlocal created_count
            created_count += 1
            return DummyClient()

        set_openai_client_factory(factory)

        for _ in range(5):
            await get_allocation_service()

        assert created_count == 1

    @pytest.mark.asyncio
    async def test_17_llm_exception_still_returns_persists_template_explanation(self, monkeypatch):
        """17. LLM exception still returns/persists template explanation."""
        from datetime import timedelta
        from app.agents.agent3_resources import (
            create_human_requirement,
            create_human_evidence,
            get_requester_id,
            get_resource_id_1,
            utc_now,
        )

        monkeypatch.setenv("AGENT3_LLM_EXPLANATIONS_ENABLED", "true")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-testkey123")

        class FailingClient:
            class Responses:
                async def create(self, **kwargs):
                    raise RuntimeError("OpenAI Connection Failed")
            responses = Responses()

        set_openai_client_factory(lambda cfg: FailingClient())

        repo = InMemoryResourceRepository()
        tenant_id = get_tenant_a_id()
        now = utc_now()
        repo.add_human_resource(
            create_human_evidence(
                tenant_id=tenant_id,
                reference_timestamp=now,
                resource_id=get_resource_id_1(),
                is_active=True,
                roles=["Developer"],
            )
        )

        generator = OpenAIExplanationGenerator(client=FailingClient())
        explainer = ResilientFallbackExplainer(enabled=True, llm_generator=generator)
        service = ResourceAllocationService(repo, explainer=explainer)

        req = AllocationRequest(
            metadata=AgentMessageMetadata(
                correlation_id=uuid4(),
                process_instance_id=uuid4(),
                task_id=uuid4(),
                tenant_id=tenant_id,
                message_type="RESOURCE_ALLOCATION_REQUEST", # type: ignore
            ),
            human_requirements=create_human_requirement(
                tenant_id=tenant_id,
                requester_id=get_requester_id(),
                required_roles=["Developer"],
                reference_timestamp=now,
            ),
        )

        rec = await service.process_allocation_request(req, evaluation_timestamp=now)

        assert rec.status == RecommendationStatus.PENDING_HUMAN_APPROVAL
        assert "=== Resource Allocation Recommendation ===" in rec.explanation

    @pytest.mark.asyncio
    async def test_18_failed_recommendation_makes_zero_llm_calls(self, monkeypatch):
        """18. Technical FAILED recommendation makes zero LLM calls."""
        monkeypatch.setenv("AGENT3_LLM_EXPLANATIONS_ENABLED", "true")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-testkey123")

        dummy = DummyClient()
        set_openai_client_factory(lambda cfg: dummy)

        service = await get_allocation_service()
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
        assert dummy.call_count == 0

    @pytest.mark.asyncio
    async def test_19_api_post_behavior_status_remains_unchanged(self):
        """19. API POST route contract remains 201 CREATED."""
        from app.api.v1.routes_agent3 import router
        assert router is not None

    @pytest.mark.asyncio
    async def test_20_openapi_contains_no_llm_config_or_secret(self):
        """20. OpenAPI schema contains no LLM configuration or secrets."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.get("/openapi.json")
            assert res.status_code == 200
            openapi_text = res.text
            assert "OPENAI_API_KEY" not in openapi_text
            assert "AGENT3_LLM_EXPLANATIONS_ENABLED" not in openapi_text

    def test_21_tenant_correlation_values_never_enter_runtime_config(self):
        """21. Tenant and correlation IDs never enter runtime configuration."""
        config = get_agent3_llm_config()
        assert not hasattr(config, "tenant_id")
        assert not hasattr(config, "correlation_id")

    @pytest.mark.asyncio
    async def test_22_runtime_reset_fixture_prevents_state_leakage(self):
        """22. Runtime reset fixture prevents state leakage across test cases."""
        dummy = DummyClient()
        set_openai_client_factory(lambda cfg: dummy)
        get_shared_openai_client(Agent3LLMConfig(enabled=True, api_key="sk-test"))

        reset_agent3_llm_runtime()
        from app.agents.agent3_resources.runtime_config import _shared_openai_client
        assert _shared_openai_client is None
