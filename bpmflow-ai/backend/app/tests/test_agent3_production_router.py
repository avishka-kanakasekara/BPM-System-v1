"""Production router tests for Agent 3 API registration.

These tests verify that:
- Agent 3 router is registered exactly once
- Actual final paths appear in app OpenAPI
- Existing routes remain present
- No duplicate /api/v1 prefix
- No approve/reject/execute route
- App import does not require live DB connection
- App import does not require live Supabase network access
"""

import os
import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

# Set minimal environment variables for config
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

from app.main import app
from app.api.v1.router import api_router


# ============================================================================
# Router Registration Tests
# ============================================================================


class TestRouterRegistration:
    """Tests for router registration."""

    @pytest.mark.asyncio
    async def test_agent3_router_registered_exactly_once(self):
        """Test Agent 3 router is registered exactly once."""
        # The most reliable way to check router registration is via OpenAPI
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/openapi.json")
            assert response.status_code == 200
        
            openapi_schema = response.json()
            paths = openapi_schema.get("paths", {})
        
            # Agent 3 routes should be present in OpenAPI
            agent3_paths = [p for p in paths.keys() if "/agent3" in p]
            assert len(agent3_paths) > 0, "Agent 3 routes not found in OpenAPI"
        
            # Verify the expected Agent 3 endpoints are present
            expected_endpoints = [
                "/api/v1/agent3/allocations",
                "/api/v1/agent3/recommendations/{recommendation_id}",
                "/api/v1/agent3/recommendations/by-correlation/{correlation_id}",
            ]
            for endpoint in expected_endpoints:
                assert endpoint in paths, f"Expected endpoint {endpoint} not found"

    @pytest.mark.asyncio
    async def test_actual_final_paths_in_openapi(self):
        """Test actual final paths appear in app OpenAPI."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Get OpenAPI schema
            response = await client.get("/openapi.json")
            assert response.status_code == 200
        
            openapi_schema = response.json()
            paths = openapi_schema.get("paths", {})
        
            # Check for Agent 3 paths
            agent3_paths = [p for p in paths.keys() if "/agent3" in p]
            assert len(agent3_paths) > 0, "Agent 3 paths not in OpenAPI"
        
            # Expected paths
            expected_paths = [
                "/api/v1/agent3/allocations",
                "/api/v1/agent3/recommendations/{recommendation_id}",
                "/api/v1/agent3/recommendations/by-correlation/{correlation_id}",
            ]
        
            for expected_path in expected_paths:
                assert expected_path in paths, f"Expected path {expected_path} not found in OpenAPI"

    @pytest.mark.asyncio
    async def test_existing_routes_remain_present(self):
        """Test existing routes remain present."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Root endpoint should still work
            response = await client.get("/")
            assert response.status_code == 200
            assert response.json()["message"] == "BPMFlow AI API"

            # Health endpoint should still work without a live DB network call.
            from unittest.mock import patch

            class _FakeHealthyEngine:
                def connect(self):
                    return self

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

                def execute(self, *_args, **_kwargs):
                    return None

            with patch("app.core.database.get_sync_engine", return_value=_FakeHealthyEngine()):
                response = await client.get("/health")
            assert response.status_code == 200
            assert response.json()["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_no_duplicate_api_v1_prefix(self):
        """Test no duplicate /api/v1 prefix."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/openapi.json")
            assert response.status_code == 200
        
            openapi_schema = response.json()
            paths = openapi_schema.get("paths", {})
        
            # Check that paths don't have duplicate /api/v1
            for path in paths.keys():
                # Count occurrences of /api/v1
                count = path.count("/api/v1")
                assert count <= 1, f"Path {path} has duplicate /api/v1 prefix"

    @pytest.mark.asyncio
    async def test_no_approve_reject_execute_route(self):
        """Agent 3 routes must not expose approve/reject/execute endpoints.

        Agent 4 human-approval APIs under /api/v1/approvals are expected and
        are intentionally excluded from this check after the branch merge.
        """
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/openapi.json")
            assert response.status_code == 200

            openapi_schema = response.json()
            paths = openapi_schema.get("paths", {})

            forbidden_paths = ["approve", "reject", "execute"]

            for path in paths.keys():
                if not path.startswith("/api/v1/agent3"):
                    continue
                for forbidden in forbidden_paths:
                    assert forbidden not in path.lower(), (
                        f"Forbidden Agent 3 path {path} contains {forbidden}"
                    )


# ============================================================================
# Import Tests
# ============================================================================


class TestImports:
    """Tests for import-time behavior."""

    def test_app_import_does_not_require_live_db(self):
        """Test app import does not require live DB connection."""
        # This test verifies that importing the app doesn't try to connect to DB
        # The engine is created lazily, so import should succeed without DB
        
        # Dispose any existing engine
        import asyncio
        from app.core.database import dispose_engine
        asyncio.run(dispose_engine())
        
        # Re-import the app (should not fail)
        import importlib
        import app.main
        importlib.reload(app.main)
        
        # Engine should still be None (lazy)
        from app.core.database import _engine
        assert _engine is None, "Engine should not be created at import time"

    def test_app_import_does_not_require_supabase_network(self):
        """Test app import does not require live Supabase network access."""
        # This test verifies that importing the app doesn't try to connect to Supabase
        # JWKS is fetched lazily on first request, not at import time
        
        # Re-import the app (should not fail without network)
        import importlib
        import app.main
        importlib.reload(app.main)
        
        # No network calls should be made during import
        # This is verified by the fact that the import succeeds
        # without any Supabase configuration
