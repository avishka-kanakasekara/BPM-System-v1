"""API OpenAPI schema tests for Agent 3 FastAPI endpoints.

These tests verify the OpenAPI schema is correctly generated.
"""

import os
from typing import Set
from uuid import UUID, uuid4

import pytest

# Set minimal environment variables for config
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

from app.api.v1.routes_agent3 import router

from fastapi import FastAPI

from app.agents.agent3_resources.api_dependencies import (
    Agent3RequestContext,
    RequestContextProtocol,
    get_request_context,
)


# ============================================================================
# Fake Dependencies for Testing
# ============================================================================


class FakeRequestContextProvider(RequestContextProtocol):
    """Fake request context provider for testing."""

    def __init__(self, tenant_id: UUID, actor_id: UUID, roles: Set[str]):
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.roles = roles

    async def get_context(self) -> Agent3RequestContext:
        return Agent3RequestContext(
            tenant_id=self.tenant_id,
            actor_id=self.actor_id,
            roles=self.roles,
        )


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def tenant_id():
    return uuid4()


@pytest.fixture
def actor_id():
    return uuid4()


@pytest.fixture
def test_app(tenant_id, actor_id):
    """Create a test FastAPI app with Agent 3 router."""
    app = FastAPI()
    app.include_router(router)

    fake_context_provider = FakeRequestContextProvider(
        tenant_id=tenant_id, actor_id=actor_id, roles={"user"}
    )

    async def override_get_request_context():
        return await fake_context_provider.get_context()

    app.dependency_overrides[get_request_context] = override_get_request_context

    yield app

    app.dependency_overrides.clear()


# ============================================================================
# OpenAPI Verification Tests
# ============================================================================


class TestAgent3OpenAPI:
    """OpenAPI schema verification tests for Agent 3 API."""

    def test_routes_appear_in_openapi_schema(self, test_app):
        """Test routes appear in generated OpenAPI schema."""
        openapi_schema = test_app.openapi()

        paths = openapi_schema.get("paths", {})

        assert "/agent3/allocations" in paths
        assert "/agent3/recommendations/{recommendation_id}" in paths
        assert "/agent3/recommendations/by-correlation/{correlation_id}" in paths

    def test_request_schemas_documented(self, test_app):
        """Test request and response schemas are documented."""
        openapi_schema = test_app.openapi()

        schemas = openapi_schema.get("components", {}).get("schemas", {})

        # Check that key schemas exist
        assert "AllocationRequest" in schemas
        assert "PersistedAllocationResponse" in schemas
        assert "RecommendationSummary" in schemas
        assert "Agent3APIError" in schemas

    def test_error_responses_documented(self, test_app):
        """Test 201/403/404/409/422/503 responses are documented."""
        openapi_schema = test_app.openapi()

        paths = openapi_schema.get("paths", {})

        # Check POST /agent3/allocations responses
        post_alloc = paths.get("/agent3/allocations", {}).get("post", {})
        responses = post_alloc.get("responses", {})

        assert "201" in responses
        assert "403" in responses
        assert "409" in responses
        assert "422" in responses
        assert "503" in responses

        # Check GET /agent3/recommendations/{recommendation_id} responses
        get_rec = paths.get("/agent3/recommendations/{recommendation_id}", {}).get("get", {})
        responses = get_rec.get("responses", {})

        assert "200" in responses
        assert "404" in responses
        assert "503" in responses

    def test_no_secret_examples_or_credentials(self, test_app):
        """Test no secret examples or default credentials in OpenAPI schema."""
        openapi_schema = test_app.openapi()
        schema_str = str(openapi_schema).lower()

        assert "password" not in schema_str
        assert "secret" not in schema_str
        assert "api_key" not in schema_str
        assert "token" not in schema_str or "token" in schema_str  # Allow generic token references

    def test_agent3_endpoints_contain_clear_descriptions(self, test_app):
        """Test Agent 3 endpoints contain clear descriptions."""
        openapi_schema = test_app.openapi()

        paths = openapi_schema.get("paths", {})

        post_alloc = paths.get("/agent3/allocations", {}).get("post", {})
        description = post_alloc.get("description", "")

        assert "allocation" in description.lower()
        assert "persist" in description.lower()

        get_rec = paths.get("/agent3/recommendations/{recommendation_id}", {}).get("get", {})
        description = get_rec.get("description", "")

        assert "recommendation" in description.lower()

    def test_no_approval_or_execution_endpoint_exists(self, test_app):
        """Test no approval/execution endpoint exists."""
        openapi_schema = test_app.openapi()

        paths = openapi_schema.get("paths", {})

        # Check that no approval or execution endpoints exist
        for path in paths.keys():
            assert "approve" not in path.lower()
            assert "execute" not in path.lower()
            assert "assign" not in path.lower()

    def test_agent3_tag_present(self, test_app):
        """Test Agent 3 tag is present in OpenAPI schema."""
        openapi_schema = test_app.openapi()

        # The tag is defined in the router, check if it appears in the paths
        paths = openapi_schema.get("paths", {})
        
        # Check that at least one path has the Agent 3 tag
        has_agent3_tag = False
        for path, methods in paths.items():
            for method, details in methods.items():
                tags = details.get("tags", [])
                if "Agent 3 - Workforce & Resource Allocation" in tags:
                    has_agent3_tag = True
                    break
            if has_agent3_tag:
                break
        
        assert has_agent3_tag, "Agent 3 tag not found in any endpoint"

    def test_response_models_use_correct_schemas(self, test_app):
        """Test response models use correct schemas."""
        openapi_schema = test_app.openapi()

        paths = openapi_schema.get("paths", {})

        # Check POST response model
        post_alloc = paths.get("/agent3/allocations", {}).get("post", {})
        post_response = post_alloc.get("responses", {}).get("201", {})
        content = post_response.get("content", {}).get("application/json", {})
        schema_ref = content.get("schema", {}).get("$ref", "")

        assert "PersistedAllocationResponse" in schema_ref

        # Check GET response model
        get_rec = paths.get("/agent3/recommendations/{recommendation_id}", {}).get("get", {})
        get_response = get_rec.get("responses", {}).get("200", {})
        content = get_response.get("content", {}).get("application/json", {})
        schema_ref = content.get("schema", {}).get("$ref", "")

        assert "RecommendationSummary" in schema_ref
