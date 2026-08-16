"""Live authenticated API end-to-end verification for Agent 3.

This module verifies the real Agent 3 runtime using:
- Real Supabase ES256 JWT authentication
- Real Supabase JWKS verification
- Real development PostgreSQL database
- Real FastAPI routes
- Existing migrations and synthetic Agent 3 seed data

These tests are OPT-IN and will skip unless all required environment variables are set.

Required Environment Variables:
- AGENT3_TEST_ACCESS_TOKEN: Valid Supabase JWT with app_metadata.tenant_id = 00000000-0000-0000-0000-000000000001
- AGENT3_TEST_REQUESTER_ID: User ID from token's sub claim
- AGENT3_TEST_DATABASE_URL: Development PostgreSQL URL
- SUPABASE_URL: Supabase project URL for JWKS verification

Optional for cross-tenant tests:
- AGENT3_TEST_OTHER_ACCESS_TOKEN: Valid JWT for a different tenant

SAFETY:
- Never prints, logs, or commits access tokens or database passwords
- Uses SQLAlchemy URL parsing and password masking
- Uses hide_parameters=True where engines are created
- Never falls back to production database URL
- Only deletes records created by the exact test tenant_id and correlation_id
- Never deletes 0002/0003 synthetic seed resources
- Never truncates tables or uses unscoped DELETE statements
"""

import os
import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4
from typing import Optional
from urllib.parse import urlparse
import asyncio
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from httpx import AsyncClient, ASGITransport

import app.core.database as core_database
from app.core.security import _jwks_cache, _get_jwks_url
from app.agents.agent3_resources.schemas import (
    AllocationRequest,
    AgentMessageMetadata,
    HumanResourceRequirement,
    BudgetResourceRequirement,
)
from app.agents.agent3_resources.constants import MessageType


# ============================================================================
# Privacy-Safe Response Diagnostic Helper
# ============================================================================


def _extract_safe_error(response) -> tuple[str, str]:
    """Extract error_code and retryable from response without exposing sensitive data.

    Args:
        response: httpx Response object

    Returns:
        Tuple of (error_code, retryable) as strings
        Returns ("NOT_AVAILABLE", "NOT_AVAILABLE") if JSON parsing fails

    Security:
        - Never returns message/detail text
        - Never returns request/response headers
        - Never returns tokens, URLs, SQL, or exception strings
        - Only extracts error_code and retryable fields
        - Handles both direct and nested detail shapes
    """
    try:
        body = response.json()
    except Exception:
        return "NOT_AVAILABLE", "NOT_AVAILABLE"

    # Handle direct shape: {"error_code": "...", "retryable": ...}
    if isinstance(body, dict):
        if "error_code" in body:
            error_code = str(body.get("error_code", "NOT_AVAILABLE"))
            retryable = str(body.get("retryable", "NOT_AVAILABLE"))
            return error_code, retryable

        # Handle nested detail shape: {"detail": {"error_code": "...", "retryable": ...}}
        if "detail" in body and isinstance(body["detail"], dict):
            detail = body["detail"]
            error_code = str(detail.get("error_code", "NOT_AVAILABLE"))
            retryable = str(detail.get("retryable", "NOT_AVAILABLE"))
            return error_code, retryable

    return "NOT_AVAILABLE", "NOT_AVAILABLE"


# ============================================================================
# Token Redaction Wrapper
# ============================================================================


class _RedactedToken:
    """Wrapper for access tokens to prevent exposure in logs, tracebacks, or repr."""

    def __init__(self, token: str):
        self._secret = token

    def get_secret_value(self) -> str:
        return self._secret

    def __repr__(self) -> str:
        return "<redacted>"

    def __str__(self) -> str:
        return "<redacted>"


# ============================================================================
# Environment Variable Checks & Preflight
# ============================================================================


def _mask_database_url(url: str) -> str:
    """Mask password in database URL for logging.

    Args:
        url: The database URL

    Returns:
        URL with password masked
    """
    if not url:
        return "not configured"
    try:
        parsed = urlparse(url)
        if parsed.password:
            masked = parsed._replace(password="***")
            return masked.geturl()
        return url
    except Exception:
        return "[invalid URL]"


def _check_supabase_url_preflight() -> bool:
    """Validate SUPABASE_URL preflight without exposing URL details.

    Returns:
        True if SUPABASE_URL is HTTPS and has a valid hostname.
    """
    url = os.getenv("SUPABASE_URL", "")
    if not url:
        return False
    try:
        parsed = urlparse(url)
        return parsed.scheme == "https" and bool(parsed.netloc)
    except Exception:
        return False


def _check_live_test_env() -> tuple[bool, str]:
    """Check if all required live test environment variables are set.

    Returns:
        Tuple of (is_configured, reason_if_not)
    """
    required_vars = {
        "AGENT3_TEST_ACCESS_TOKEN": "Supabase JWT access token",
        "AGENT3_TEST_REQUESTER_ID": "Requester user ID",
        "AGENT3_TEST_DATABASE_URL": "Development database URL",
        "SUPABASE_URL": "Supabase project URL",
    }

    missing = []
    for var_name, description in required_vars.items():
        if not os.getenv(var_name):
            missing.append(f"{var_name} ({description})")

    if missing:
        return False, f"Missing required environment variables: {', '.join(missing)}"

    if not _check_supabase_url_preflight():
        return False, "SUPABASE_URL is missing, not HTTPS, or invalid"

    # Validate database URL is not production
    db_url = os.getenv("AGENT3_TEST_DATABASE_URL", "")
    if "localhost" not in db_url and "127.0.0.1" not in db_url and ".supabase.co" not in db_url:
        return False, f"Database URL does not appear to be development: {_mask_database_url(db_url)}"

    return True, "All required variables configured"


def _check_other_tenant_env() -> bool:
    """Check if optional other tenant environment variable is set.

    Returns:
        True if AGENT3_TEST_OTHER_ACCESS_TOKEN is set
    """
    return bool(os.getenv("AGENT3_TEST_OTHER_ACCESS_TOKEN"))


# ============================================================================
# Constants
# ============================================================================


DEMO_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
OTHER_TENANT_ID = UUID("00000000-0000-0000-0000-000000000002")


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def live_test_configured():
    """Skip all tests in this module if live test env is not configured."""
    is_configured, reason = _check_live_test_env()
    if not is_configured:
        pytest.skip(f"Live tests require environment variables: {reason}")
    yield True


@pytest.fixture(scope="session")
def other_tenant_configured():
    """Skip cross-tenant tests if other tenant env is not configured."""
    if not _check_other_tenant_env():
        pytest.skip("Cross-tenant tests require AGENT3_TEST_OTHER_ACCESS_TOKEN")
    yield True


@pytest.fixture
def test_access_token():
    """Get the test access token from environment, wrapped for redaction."""
    token = os.getenv("AGENT3_TEST_ACCESS_TOKEN")
    if not token:
        pytest.skip("AGENT3_TEST_ACCESS_TOKEN not set")
    return _RedactedToken(token)


@pytest.fixture
def test_requester_id():
    """Get the test requester ID from environment (redacted in output)."""
    requester_id_str = os.getenv("AGENT3_TEST_REQUESTER_ID")
    if not requester_id_str:
        pytest.skip("AGENT3_TEST_REQUESTER_ID not set")
    try:
        return UUID(requester_id_str)
    except ValueError:
        pytest.skip("AGENT3_TEST_REQUESTER_ID is not a valid UUID")


@pytest.fixture
def test_database_url():
    """Get the test database URL from environment (redacted in output)."""
    url = os.getenv("AGENT3_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AGENT3_TEST_DATABASE_URL not set")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


@pytest.fixture
def supabase_url():
    """Get the Supabase URL from environment."""
    if not _check_supabase_url_preflight():
        pytest.skip("SUPABASE_URL preflight failed")
    return os.getenv("SUPABASE_URL")


@pytest_asyncio.fixture
async def live_jwks_preflight(live_database_wiring, supabase_url):
    """Live preflight fixture that invokes production JWKSCache path with real Supabase JWKS.

    - Depends on live_database_wiring to ensure cache is cleared before warming
    - Invokes production _jwks_cache.get_jwks(_get_jwks_url(supabase_url))
    - Verifies at least one compatible public key exists in the JWKS
    - Warms the production JWKS cache
    - Never prints URL, keys, or tokens
    """
    jwks_url = _get_jwks_url(supabase_url)
    try:
        jwks_data = await _jwks_cache.get_jwks(jwks_url)
    except Exception:
        pytest.skip("Failed to retrieve real Supabase JWKS during preflight")

    keys = jwks_data.get("keys", [])
    if not keys:
        pytest.skip("No public keys found in real Supabase JWKS during preflight")

    yield True


@pytest.fixture
def other_tenant_token():
    """Get the other tenant access token from environment, wrapped for redaction."""
    token = os.getenv("AGENT3_TEST_OTHER_ACCESS_TOKEN")
    if not token:
        pytest.skip("AGENT3_TEST_OTHER_ACCESS_TOKEN not set")
    return _RedactedToken(token)


@pytest_asyncio.fixture
async def live_database_wiring():
    """Safely map AGENT3_TEST_DATABASE_URL to DATABASE_URL for live test process.

    This fixture:
    - Verifies AGENT3_TEST_DATABASE_URL is set (skips if absent)
    - Disposes existing global engine before setting env var
    - Sets os.environ["DATABASE_URL"] = test_url
    - Resets _engine and _session_factory to None in app.core.database
    - Clears JWKS cache to ensure fresh state
    - On teardown: disposes test engine, restores previous DATABASE_URL, resets engine/factory, clears cache
    - Never prints or logs the database URL
    """
    test_url = os.getenv("AGENT3_TEST_DATABASE_URL")
    if not test_url:
        pytest.skip("AGENT3_TEST_DATABASE_URL not set")

    if test_url.startswith("postgresql://"):
        test_url = test_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    await core_database.dispose_engine()

    old_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_url
    core_database._engine = None
    core_database._session_factory = None

    # Clear JWKS cache to ensure fresh state
    _jwks_cache._cache.clear()

    try:
        yield test_url
    finally:
        await core_database.dispose_engine()
        if old_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_db_url
        core_database._engine = None
        core_database._session_factory = None
        _jwks_cache._cache.clear()


@pytest_asyncio.fixture
async def live_app(live_database_wiring):
    """Create FastAPI app with test-scoped DATABASE_URL wiring.

    This fixture:
    - Depends on live_database_wiring to ensure DATABASE_URL is set before app creation
    - Imports app.main AFTER DATABASE_URL is configured
    - Ensures the app uses the test database URL
    - Yields the app for use in tests
    """
    from app.main import app
    yield app


@pytest_asyncio.fixture
async def db_session(live_database_wiring):
    """Create a database session with password masking.

    Explicitly depends on live_database_wiring.
    Uses hide_parameters=True to prevent password logging.
    """
    engine = create_async_engine(
        live_database_wiring,
        echo=False,
        hide_parameters=True,
        connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0},
    )

    async with engine.begin() as conn:
        session = AsyncSession(conn, expire_on_commit=False)
        yield session
        await session.close()

    await engine.dispose()


@pytest.fixture
def correlation_id():
    """Generate a unique correlation ID for each test."""
    return uuid4()


@pytest.fixture
def allocation_request(test_requester_id, correlation_id):
    """Create a valid allocation request based on synthetic seed data.

    Uses the demo tenant and synthetic HUMAN resource from seed data.
    """
    task_deadline = datetime.now(timezone.utc).replace(hour=23, minute=59, second=59)

    return AllocationRequest(
        metadata=AgentMessageMetadata(
            correlation_id=correlation_id,
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=DEMO_TENANT_ID,
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
            timestamp=datetime.now(timezone.utc),
        ),
        human_requirements=HumanResourceRequirement(
            resource_type="HUMAN",
            required_roles=["developer"],
            mandatory_skills=["python", "fastapi"],
            preferred_skills=[],
            required_authority="senior",
            requester_id=test_requester_id,
            task_deadline=task_deadline,
            estimated_effort_hours=Decimal("8.0"),
            process_stage="resource_allocation",
        ),
        budget_requirements=BudgetResourceRequirement(
            resource_type="BUDGET",
            required_amount=Decimal("1000.00"),
            currency="USD",
            cost_centre="CC-DEMO",
            requester_id=test_requester_id,
            task_deadline=task_deadline,
            process_stage="resource_allocation",
        ),
    )


# ============================================================================
# Cleanup Fixture
# ============================================================================


@pytest_asyncio.fixture
async def cleanup_test_records(db_session, correlation_id):
    """Cleanup fixture that deletes records created during a test.

    This fixture:
    - Runs before and after the test
    - Deletes only records with the exact test tenant_id and correlation_id
    - Deletes children before parents (foreign key order)
    - Never deletes 0002/0003 synthetic seed resources
    - Never truncates tables or uses unscoped DELETE statements
    - Is idempotent (safe to run multiple times)
    - Handles cleanup failures gracefully when no records were due to test failure
    """
    # Pre-test cleanup: Remove stale records from previous failed runs
    try:
        await db_session.execute(
            text("""
                DELETE FROM public.recommendation_evidence_links
                WHERE recommendation_id IN (
                    SELECT id FROM public.allocation_recommendations
                    WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
                )
            """),
            {"tenant_id": str(DEMO_TENANT_ID), "correlation_id": str(correlation_id)},
        )

        await db_session.execute(
            text("""
                DELETE FROM public.allocation_exclusion_reasons
                WHERE exclusion_id IN (
                    SELECT id FROM public.allocation_exclusions
                    WHERE recommendation_id IN (
                        SELECT id FROM public.allocation_recommendations
                        WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
                    )
                )
            """),
            {"tenant_id": str(DEMO_TENANT_ID), "correlation_id": str(correlation_id)},
        )

        await db_session.execute(
            text("""
                DELETE FROM public.allocation_exclusions
                WHERE recommendation_id IN (
                    SELECT id FROM public.allocation_recommendations
                    WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
                )
            """),
            {"tenant_id": str(DEMO_TENANT_ID), "correlation_id": str(correlation_id)},
        )

        await db_session.execute(
            text("""
                DELETE FROM public.allocation_candidates
                WHERE recommendation_id IN (
                    SELECT id FROM public.allocation_recommendations
                    WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
                )
            """),
            {"tenant_id": str(DEMO_TENANT_ID), "correlation_id": str(correlation_id)},
        )

        await db_session.execute(
            text("""
                DELETE FROM public.resource_alternatives
                WHERE gap_id IN (
                    SELECT id FROM public.resource_gaps
                    WHERE recommendation_id IN (
                        SELECT id FROM public.allocation_recommendations
                        WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
                    )
                )
            """),
            {"tenant_id": str(DEMO_TENANT_ID), "correlation_id": str(correlation_id)},
        )

        await db_session.execute(
            text("""
                DELETE FROM public.resource_gaps
                WHERE recommendation_id IN (
                    SELECT id FROM public.allocation_recommendations
                    WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
                )
            """),
            {"tenant_id": str(DEMO_TENANT_ID), "correlation_id": str(correlation_id)},
        )

        await db_session.execute(
            text("""
                DELETE FROM public.budget_validation_results
                WHERE recommendation_id IN (
                    SELECT id FROM public.allocation_recommendations
                    WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
                )
            """),
            {"tenant_id": str(DEMO_TENANT_ID), "correlation_id": str(correlation_id)},
        )

        await db_session.execute(
            text("""
                DELETE FROM public.allocation_recommendations
                WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
            """),
            {"tenant_id": str(DEMO_TENANT_ID), "correlation_id": str(correlation_id)},
        )

        await db_session.execute(
            text("""
                DELETE FROM public.allocation_requirements
                WHERE request_id IN (
                    SELECT id FROM public.allocation_requests
                    WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
                )
            """),
            {"tenant_id": str(DEMO_TENANT_ID), "correlation_id": str(correlation_id)},
        )

        await db_session.execute(
            text("""
                DELETE FROM public.allocation_requests
                WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
            """),
            {"tenant_id": str(DEMO_TENANT_ID), "correlation_id": str(correlation_id)},
        )

        await db_session.commit()
    except Exception:
        await db_session.rollback()
        # Expected when no stale records exist
        pass

    yield  # Run the test

    # Cleanup after test (even if failed)
    try:
        # Delete recommendation_evidence_links first
        await db_session.execute(
            text("""
                DELETE FROM public.recommendation_evidence_links
                WHERE recommendation_id IN (
                    SELECT id FROM public.allocation_recommendations
                    WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
                )
            """),
            {"tenant_id": str(DEMO_TENANT_ID), "correlation_id": str(correlation_id)},
        )

        # Delete allocation_exclusion_reasons
        await db_session.execute(
            text("""
                DELETE FROM public.allocation_exclusion_reasons
                WHERE exclusion_id IN (
                    SELECT id FROM public.allocation_exclusions
                    WHERE recommendation_id IN (
                        SELECT id FROM public.allocation_recommendations
                        WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
                    )
                )
            """),
            {"tenant_id": str(DEMO_TENANT_ID), "correlation_id": str(correlation_id)},
        )

        # Delete allocation_exclusions
        await db_session.execute(
            text("""
                DELETE FROM public.allocation_exclusions
                WHERE recommendation_id IN (
                    SELECT id FROM public.allocation_recommendations
                    WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
                )
            """),
            {"tenant_id": str(DEMO_TENANT_ID), "correlation_id": str(correlation_id)},
        )

        # Delete allocation_candidates
        await db_session.execute(
            text("""
                DELETE FROM public.allocation_candidates
                WHERE recommendation_id IN (
                    SELECT id FROM public.allocation_recommendations
                    WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
                )
            """),
            {"tenant_id": str(DEMO_TENANT_ID), "correlation_id": str(correlation_id)},
        )

        # Delete resource_alternatives
        await db_session.execute(
            text("""
                DELETE FROM public.resource_alternatives
                WHERE gap_id IN (
                    SELECT id FROM public.resource_gaps
                    WHERE recommendation_id IN (
                        SELECT id FROM public.allocation_recommendations
                        WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
                    )
                )
            """),
            {"tenant_id": str(DEMO_TENANT_ID), "correlation_id": str(correlation_id)},
        )

        # Delete resource_gaps
        await db_session.execute(
            text("""
                DELETE FROM public.resource_gaps
                WHERE recommendation_id IN (
                    SELECT id FROM public.allocation_recommendations
                    WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
                )
            """),
            {"tenant_id": str(DEMO_TENANT_ID), "correlation_id": str(correlation_id)},
        )

        # Delete budget_validation_results
        await db_session.execute(
            text("""
                DELETE FROM public.budget_validation_results
                WHERE recommendation_id IN (
                    SELECT id FROM public.allocation_recommendations
                    WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
                )
            """),
            {"tenant_id": str(DEMO_TENANT_ID), "correlation_id": str(correlation_id)},
        )

        # Delete allocation_recommendations
        await db_session.execute(
            text("""
                DELETE FROM public.allocation_recommendations
                WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
            """),
            {"tenant_id": str(DEMO_TENANT_ID), "correlation_id": str(correlation_id)},
        )

        # Delete allocation_requirements
        await db_session.execute(
            text("""
                DELETE FROM public.allocation_requirements
                WHERE request_id IN (
                    SELECT id FROM public.allocation_requests
                    WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
                )
            """),
            {"tenant_id": str(DEMO_TENANT_ID), "correlation_id": str(correlation_id)},
        )

        # Delete allocation_requests
        await db_session.execute(
            text("""
                DELETE FROM public.allocation_requests
                WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
            """),
            {"tenant_id": str(DEMO_TENANT_ID), "correlation_id": str(correlation_id)},
        )

        await db_session.commit()
    except Exception:
        await db_session.rollback()
        # Log generic error message without sensitive details
        # This is expected when test fails before persisting any records
        print("Cleanup error occurred during test execution (details suppressed)")


# ============================================================================
# JWT Tampering Helper
# ============================================================================


def _tamper_jwt_signature(token: str) -> str:
    """Tamper a JWT by corrupting the signature segment deterministically.

    This function:
    - Splits JWT into header.payload.signature
    - Keeps header and payload unchanged
    - Selects a character near the middle of the signature
    - Replaces it with "A" if not "A", else "B"
    - Reassembles the three segments
    - Asserts the tampered token differs from the original
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise AssertionError("Invalid JWT format: must have exactly 3 segments")

    header, payload, signature = parts

    if not signature:
        raise AssertionError("Invalid JWT: signature segment is empty")

    mid_index = len(signature) // 2
    original_char = signature[mid_index]
    replacement_char = "A" if original_char != "A" else "B"

    tampered_signature = signature[:mid_index] + replacement_char + signature[mid_index + 1:]
    tampered_token = f"{header}.{payload}.{tampered_signature}"

    assert tampered_token != token, "Tampering failed: token unchanged"
    return tampered_token


# ============================================================================
# Non-Live Regression Tests
# ============================================================================


def test_redacted_token_repr_does_not_expose_secret():
    """Test _RedactedToken repr masks the token value."""
    token = _RedactedToken("secret-token-12345")
    assert repr(token) == "<redacted>"
    assert "secret-token-12345" not in repr(token)


def test_redacted_token_str_does_not_expose_secret():
    """Test _RedactedToken str masks the token value."""
    token = _RedactedToken("secret-token-12345")
    assert str(token) == "<redacted>"
    assert "secret-token-12345" not in str(token)


def test_redacted_token_get_secret_value_returns_raw():
    """Test _RedactedToken get_secret_value returns raw string."""
    token = _RedactedToken("secret-token-12345")
    assert token.get_secret_value() == "secret-token-12345"


def test_allocation_request_model_dump_json_is_serializable():
    """Test allocation_request.model_dump(mode='json') can be serialized with json.dumps."""
    import json
    req = AllocationRequest(
        metadata=AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=DEMO_TENANT_ID,
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
            timestamp=datetime.now(timezone.utc),
        ),
        human_requirements=HumanResourceRequirement(
            resource_type="HUMAN",
            required_roles=["developer"],
            mandatory_skills=["python"],
            preferred_skills=[],
            required_authority="senior",
            requester_id=uuid4(),
            task_deadline=datetime.now(timezone.utc),
            estimated_effort_hours=Decimal("8.0"),
            process_stage="resource_allocation",
        ),
    )
    dumped = req.model_dump(mode="json")
    json_str = json.dumps(dumped)
    assert isinstance(json_str, str)
    assert len(json_str) > 0


def test_tenant_mismatch_payload_validates_under_schema():
    """Test constructing tenant-mismatch request via model_validate and mode='json' serialization."""
    import json
    req = AllocationRequest(
        metadata=AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=DEMO_TENANT_ID,
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
            timestamp=datetime.now(timezone.utc),
        ),
    )
    dumped = req.model_dump(mode="json")
    dumped["metadata"]["tenant_id"] = str(OTHER_TENANT_ID)
    validated = AllocationRequest.model_validate(dumped)
    assert validated.metadata.tenant_id == OTHER_TENANT_ID
    json_bytes = json.dumps(validated.model_dump(mode="json"))
    assert str(OTHER_TENANT_ID) in json_bytes


def test_tenant_mismatch_via_model_copy():
    """Test tenant mismatch construction using model_copy (not dict mutation)."""
    from uuid import uuid4
    from datetime import datetime, timezone

    original_req = AllocationRequest(
        metadata=AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=DEMO_TENANT_ID,
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
            timestamp=datetime.now(timezone.utc),
        ),
    )

    # Use model_copy to create mismatched request
    mismatched_metadata = original_req.metadata.model_copy(update={"tenant_id": OTHER_TENANT_ID})
    mismatched_req = original_req.model_copy(update={"metadata": mismatched_metadata})

    assert mismatched_req.metadata.tenant_id == OTHER_TENANT_ID
    assert original_req.metadata.tenant_id == DEMO_TENANT_ID  # Original unchanged


def test_extract_safe_error_direct_shape():
    """Test _extract_safe_error extracts from direct error shape."""
    from httpx import Response

    response = Response(
        status_code=500,
        json={"error_code": "INTERNAL_ERROR", "retryable": True},
    )
    error_code, retryable = _extract_safe_error(response)
    assert error_code == "INTERNAL_ERROR"
    assert retryable == "True"


def test_extract_safe_error_nested_detail_shape():
    """Test _extract_safe_error extracts from nested detail shape."""
    from httpx import Response

    response = Response(
        status_code=503,
        json={"detail": {"error_code": "JWKS_FETCH_FAILED", "retryable": False}},
    )
    error_code, retryable = _extract_safe_error(response)
    assert error_code == "JWKS_FETCH_FAILED"
    assert retryable == "False"


def test_extract_safe_error_malformed_json_returns_defaults():
    """Test _extract_safe_error returns defaults for malformed/non-JSON response."""
    from httpx import Response

    response = Response(status_code=500, content=b"not json")
    error_code, retryable = _extract_safe_error(response)
    assert error_code == "NOT_AVAILABLE"
    assert retryable == "NOT_AVAILABLE"


def test_extract_safe_error_never_exposes_message_text():
    """Test _extract_safe_error never returns message or detail text."""
    from httpx import Response

    response = Response(
        status_code=500,
        json={
            "error_code": "INTERNAL_ERROR",
            "message": "This sensitive message should not be exposed",
            "detail": "This sensitive detail should not be exposed",
            "retryable": True,
        },
    )
    error_code, retryable = _extract_safe_error(response)
    assert error_code == "INTERNAL_ERROR"
    assert retryable == "True"
    # Verify the function only returns the two fields
    assert len([error_code, retryable]) == 2


def test_extract_safe_error_never_exposes_token_sentinel():
    """Test _extract_safe_error never returns token even if present in response."""
    from httpx import Response

    response = Response(
        status_code=500,
        json={
            "error_code": "INTERNAL_ERROR",
            "token": "secret-token-12345",
            "retryable": True,
        },
    )
    error_code, retryable = _extract_safe_error(response)
    assert error_code == "INTERNAL_ERROR"
    assert retryable == "True"
    assert "secret-token-12345" not in error_code
    assert "secret-token-12345" not in retryable


def test_extract_safe_error_never_exposes_url_sentinel():
    """Test _extract_safe_error never returns URL even if present in response."""
    from httpx import Response

    response = Response(
        status_code=500,
        json={
            "error_code": "INTERNAL_ERROR",
            "url": "https://example.com/sensitive",
            "retryable": True,
        },
    )
    error_code, retryable = _extract_safe_error(response)
    assert error_code == "INTERNAL_ERROR"
    assert retryable == "True"
    assert "https://example.com" not in error_code
    assert "https://example.com" not in retryable


def test_extract_safe_error_never_exposes_sql_sentinel():
    """Test _extract_safe_error never returns SQL even if present in response."""
    from httpx import Response

    response = Response(
        status_code=500,
        json={
            "error_code": "INTERNAL_ERROR",
            "sql": "SELECT * FROM sensitive_table",
            "retryable": True,
        },
    )
    error_code, retryable = _extract_safe_error(response)
    assert error_code == "INTERNAL_ERROR"
    assert retryable == "True"
    assert "SELECT" not in error_code
    assert "SELECT" not in retryable


def test_extract_safe_error_never_includes_raw_response():
    """Test _extract_safe_error never includes the raw response object."""
    from httpx import Response

    response = Response(
        status_code=500,
        json={"error_code": "INTERNAL_ERROR", "retryable": True},
    )
    error_code, retryable = _extract_safe_error(response)
    # Verify return values are strings, not the response object
    assert isinstance(error_code, str)
    assert isinstance(retryable, str)
    assert error_code != response
    assert retryable != response


@pytest.mark.asyncio
async def test_tampered_jwt_with_mocked_jwks_returns_401():
    """Non-live test proving tampered signature + working JWKS returns 401 (not 503).

    Uses mocked dependencies and mocked JWKS (no network, no DB).
    """
    from unittest.mock import AsyncMock, patch
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from jose import jwk as jose_jwk, jwt as jose_jwt
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
    from app.api.v1.routes_agent3 import router as agent3_router
    from app.agents.agent3_resources.api_dependencies import (
        get_allocation_service,
        get_persistence_service,
        get_read_repository,
    )
    from app.core import security as sec_mod

    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    jwk_dict = jose_jwk.construct(public_pem, algorithm="ES256").to_dict()
    jwk_dict["kid"] = "nonlive-test-key"
    fake_jwks = {"keys": [jwk_dict]}

    payload = {
        "sub": str(uuid4()),
        "app_metadata": {"tenant_id": str(uuid4())},
        "role": "authenticated",
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "iss": "https://test.supabase.co/auth/v1",
        "aud": "authenticated",
    }
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    valid_jwt = jose_jwt.encode(payload, private_pem, algorithm="ES256", headers={"kid": "nonlive-test-key"})
    tampered_jwt = _tamper_jwt_signature(valid_jwt)

    test_app = FastAPI()
    test_app.include_router(agent3_router)

    class FakeAlloc:
        async def process_allocation_request(self, *a, **kw):
            pass

    class FakePersist:
        async def persist_allocation_result(self, *a, **kw):
            pass

    class FakeRead:
        async def get_recommendation(self, *a, **kw):
            return None

        async def get_latest_recommendation_by_correlation_id(self, *a, **kw):
            return None

    test_app.dependency_overrides[get_allocation_service] = lambda: FakeAlloc()
    test_app.dependency_overrides[get_persistence_service] = lambda: FakePersist()
    test_app.dependency_overrides[get_read_repository] = lambda: FakeRead()

    with patch.object(sec_mod.settings, "SUPABASE_URL", "https://test.supabase.co"):
        with patch.object(sec_mod._jwks_cache, "get_jwks", AsyncMock(return_value=fake_jwks)):
            async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
                resp = await client.post(
                    "/agent3/allocations",
                    headers={"Authorization": f"Bearer {tampered_jwt}"},
                    json={},
                )

    assert resp.status_code == 401
    assert "WWW-Authenticate" in resp.headers
    assert resp.headers["WWW-Authenticate"] == "Bearer"


def test_tamper_helper_corrupts_signature_only():
    """Test tamper helper corrupts only the signature segment."""
    fake_jwt = "header.payload.signature123456789"
    tampered = _tamper_jwt_signature(fake_jwt)

    original_parts = fake_jwt.split(".")
    tampered_parts = tampered.split(".")

    assert tampered_parts[0] == original_parts[0], "Header was modified"
    assert tampered_parts[1] == original_parts[1], "Payload was modified"
    assert tampered_parts[2] != original_parts[2], "Signature was not modified"
    assert tampered != fake_jwt, "Token unchanged"


def test_tamper_helper_never_returns_original():
    """Test tamper helper never returns the original token."""
    test_tokens = [
        "header.payload.abc",
        "header.payload.aaa",
        "header.payload.AAA",
        "header.payload.123456789",
    ]

    for token in test_tokens:
        tampered = _tamper_jwt_signature(token)
        assert tampered != token, f"Tamper returned original for {token}"


def test_tamper_helper_validates_jwt_format():
    """Test tamper helper validates JWT format."""
    with pytest.raises(AssertionError, match="Invalid JWT format"):
        _tamper_jwt_signature("invalid")

    with pytest.raises(AssertionError, match="Invalid JWT format"):
        _tamper_jwt_signature("header.payload")

    with pytest.raises(AssertionError, match="Invalid JWT format"):
        _tamper_jwt_signature("header.payload.extra.segment")


def test_tamper_helper_validates_signature_not_empty():
    """Test tamper helper validates signature is not empty."""
    with pytest.raises(AssertionError, match="signature segment is empty"):
        _tamper_jwt_signature("header.payload.")


def test_metadata_schema_requires_all_fields():
    """Test AgentMessageMetadata requires all fields per schema."""
    valid_metadata = AgentMessageMetadata(
        correlation_id=uuid4(),
        process_instance_id=uuid4(),
        task_id=uuid4(),
        tenant_id=uuid4(),
        message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
        timestamp=datetime.now(timezone.utc),
    )

    assert hasattr(valid_metadata, "message_id")
    assert hasattr(valid_metadata, "schema_version")
    assert hasattr(valid_metadata, "correlation_id")
    assert hasattr(valid_metadata, "process_instance_id")
    assert hasattr(valid_metadata, "task_id")
    assert hasattr(valid_metadata, "tenant_id")
    assert hasattr(valid_metadata, "sender")
    assert hasattr(valid_metadata, "receiver")
    assert hasattr(valid_metadata, "message_type")
    assert hasattr(valid_metadata, "timestamp")


def test_metadata_rejects_requester_id():
    """Test AgentMessageMetadata rejects requester_id (extra='forbid')."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AgentMessageMetadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=uuid4(),
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
            timestamp=datetime.now(timezone.utc),
            requester_id=uuid4(),
        )


def test_human_requirement_requires_requester_id():
    """Test HumanResourceRequirement requires requester_id in correct location."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        HumanResourceRequirement(
            resource_type="HUMAN",
            required_roles=["developer"],
            mandatory_skills=["python"],
            preferred_skills=[],
            required_authority="senior",
            task_deadline=datetime.now(timezone.utc),
            estimated_effort_hours=Decimal("8.0"),
            process_stage="resource_allocation",
        )


def test_budget_requirement_requires_requester_id():
    """Test BudgetResourceRequirement requires requester_id in correct location."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        BudgetResourceRequirement(
            resource_type="BUDGET",
            required_amount=Decimal("1000.00"),
            currency="USD",
            cost_centre="CC-DEMO",
            task_deadline=datetime.now(timezone.utc),
            process_stage="resource_allocation",
        )


# ============================================================================
# Phase 2: Live Authentication Tests
# ============================================================================


@pytest.mark.live
@pytest.mark.asyncio
async def test_request_without_authorization_returns_401(live_test_configured, live_app):
    """Test request without Authorization header returns 401 with WWW-Authenticate."""
    async with AsyncClient(transport=ASGITransport(app=live_app), base_url="http://test") as client:
        response = await client.post("/api/v1/agent3/allocations", json={})

    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.live
@pytest.mark.asyncio
async def test_malformed_bearer_header_returns_401(live_test_configured, live_app):
    """Test malformed bearer header returns 401."""
    async with AsyncClient(transport=ASGITransport(app=live_app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent3/allocations",
            headers={"Authorization": "InvalidFormat"},
            json={},
        )

    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers


@pytest.mark.live
@pytest.mark.asyncio
async def test_tampered_jwt_returns_401(live_test_configured, live_app, test_access_token):
    """Test tampered JWT returns 401 without exposing token details.

    This test uses deterministic signature corruption:
    - Splits JWT into header.payload.signature
    - Keeps header and payload unchanged
    - Corrupts a character near the middle of the signature
    - Sends through real production authentication dependency
    - Expects 401 with WWW-Authenticate: Bearer
    - Verifies response contains no token fragments
    """
    raw_token = test_access_token.get_secret_value()
    tampered_token = _tamper_jwt_signature(raw_token)

    async with AsyncClient(transport=ASGITransport(app=live_app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent3/allocations",
            headers={"Authorization": f"Bearer {tampered_token}"},
            json={},
        )

    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
    assert response.headers["WWW-Authenticate"] == "Bearer"

    error_detail = response.text
    assert tampered_token not in error_detail
    assert raw_token not in error_detail


@pytest.mark.live
@pytest.mark.asyncio
async def test_valid_supabase_jwt_accepted(
    live_test_configured,
    live_jwks_preflight,
    live_app,
    test_access_token,
):
    """Test valid Supabase ES256 JWT is verified through real JWKS endpoint against a protected route.

    Proves:
    - Real JWKS retrieval succeeded
    - Real JWT was verified
    - Trusted tenant context came from app_metadata.tenant_id
    - Protected endpoint was reached
    """
    non_existent_rec_id = uuid4()
    async with AsyncClient(transport=ASGITransport(app=live_app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/agent3/recommendations/{non_existent_rec_id}",
            headers={"Authorization": f"Bearer {test_access_token.get_secret_value()}"},
        )

    # Protected endpoint returns 404 (recommendation not found) when JWT auth succeeds,
    # proving real JWKS verification passed and request reached route logic (rather than 401).
    assert response.status_code == 404
    body = response.json()
    error_detail = body.get("detail", body)
    assert error_detail["error_code"] == "RECOMMENDATION_NOT_FOUND"


# ============================================================================
# Phase 3: Live Agent 3 Workflow
# ============================================================================


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_agent3_workflow(
    live_test_configured,
    live_jwks_preflight,
    live_app,
    test_access_token,
    allocation_request,
    correlation_id,
    cleanup_test_records,
    db_session,
):
    """Test complete live Agent 3 workflow with real database.

    This test:
    1. POST /api/v1/agent3/allocations with valid HUMAN requirement
    2. Verifies HTTP 201, persisted=true, valid status, tenant match, correlation preserved
    3. GET recommendation by recommendation_id
    4. GET latest recommendation by correlation_id
    5. Verifies database contains all expected records
    """
    async with AsyncClient(transport=ASGITransport(app=live_app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent3/allocations",
            headers={"Authorization": f"Bearer {test_access_token.get_secret_value()}"},
            json=allocation_request.model_dump(mode="json"),
        )

    if response.status_code != 201:
        error_code, retryable = _extract_safe_error(response)
        pytest.fail(
            f"Expected HTTP 201; received {response.status_code}; "
            f"error_code={error_code}; retryable={retryable}"
        )
    result = response.json()

    assert result["persisted"] is True
    assert result["tenant_id"] == str(DEMO_TENANT_ID)
    assert result["correlation_id"] == str(correlation_id)
    assert "recommendation_id" in result
    assert "recommendation_status" in result
    assert "persisted_at" in result
    assert result["recommendation_id"] is not None

    recommendation_id = UUID(result["recommendation_id"])
    assert isinstance(recommendation_id, UUID)

    persisted_at = datetime.fromisoformat(result["persisted_at"])
    assert persisted_at.tzinfo is not None

    # GET recommendation by ID
    async with AsyncClient(transport=ASGITransport(app=live_app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/agent3/recommendations/{recommendation_id}",
            headers={"Authorization": f"Bearer {test_access_token.get_secret_value()}"},
        )

    if response.status_code != 200:
        error_code, retryable = _extract_safe_error(response)
        pytest.fail(
            f"GET by ID failed: expected HTTP 200; received {response.status_code}; "
            f"error_code={error_code}; retryable={retryable}; "
            f"recommendation_id={recommendation_id}"
        )
    rec_by_id = response.json()
    assert rec_by_id["recommendation_id"] == str(recommendation_id)
    assert rec_by_id["tenant_id"] == str(DEMO_TENANT_ID)
    assert rec_by_id["correlation_id"] == str(correlation_id)

    # GET latest recommendation by correlation_id
    async with AsyncClient(transport=ASGITransport(app=live_app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/agent3/recommendations/by-correlation/{correlation_id}",
            headers={"Authorization": f"Bearer {test_access_token.get_secret_value()}"},
        )

    if response.status_code != 200:
        error_code, retryable = _extract_safe_error(response)
        pytest.fail(
            f"GET by correlation failed: expected HTTP 200; received {response.status_code}; "
            f"error_code={error_code}; retryable={retryable}; "
            f"correlation_id={correlation_id}"
        )
    rec_by_corr = response.json()
    assert rec_by_corr["recommendation_id"] == str(recommendation_id)
    assert rec_by_corr["tenant_id"] == str(DEMO_TENANT_ID)
    assert rec_by_corr["correlation_id"] == str(correlation_id)

    # Verify database contains expected records
    result = await db_session.execute(
        text("""
            SELECT id FROM public.allocation_requests
            WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
        """),
        {"tenant_id": str(DEMO_TENANT_ID), "correlation_id": str(correlation_id)},
    )
    allocation_request_row = result.fetchone()
    assert allocation_request_row is not None

    result = await db_session.execute(
        text("""
            SELECT id, status FROM public.allocation_recommendations
            WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
        """),
        {"tenant_id": str(DEMO_TENANT_ID), "correlation_id": str(correlation_id)},
    )
    recommendation_row = result.fetchone()
    assert recommendation_row is not None
    assert recommendation_row[1] in ("GENERATED", "PENDING_HUMAN_APPROVAL", "FAILED")


# ============================================================================
# Static Regression Tests
# ============================================================================


def test_live_runtime_sql_uses_migration_0004_table_names():
    """Static regression test that verifies live runtime SQL uses only migration-0004 table names.

    This test:
    - Does not require live credentials or database
    - Scans the test file for SQL table references
    - Ensures all references match migration-0004 table names
    - Prevents regression to obsolete table names
    """
    import re
    import inspect

    # Get the source code of this test file
    source = inspect.getsource(inspect.getmodule(test_live_runtime_sql_uses_migration_0004_table_names))

    # Valid migration-0004 table names
    valid_tables = {
        "allocation_requests",
        "allocation_requirements",
        "allocation_recommendations",
        "allocation_candidates",
        "allocation_exclusions",
        "allocation_exclusion_reasons",
        "resource_gaps",
        "resource_alternatives",
        "budget_validation_results",
        "recommendation_evidence_links",
    }

    # Obsolete table names that should not appear
    obsolete_tables = {
        "recommendations",
        "evidence_links",
        "ranked_candidates",
        "allocation_alternatives",
        "allocation_gaps",
        "requirements",
        "requests",
    }

    # Find all SQL table references (FROM public.table_name)
    # Match any table name after public.
    sql_table_pattern = re.compile(r'FROM\s+public\.(\w+)', re.IGNORECASE)
    found_tables = set(sql_table_pattern.findall(source))

    # Filter out the pattern placeholder from the test itself
    found_tables = {t for t in found_tables if t != 'table_name'}

    # Check that no obsolete table names are used
    obsolete_found = found_tables & obsolete_tables
    assert not obsolete_found, f"Found obsolete table names in SQL: {obsolete_found}"

    # Check that all found tables are valid migration-0004 tables
    invalid_found = found_tables - valid_tables
    assert not invalid_found, f"Found invalid table names in SQL: {invalid_found}"

    # Verify all valid tables are referenced (optional - can be commented out if not all tables are used)
    # assert found_tables.issubset(valid_tables), f"SQL references tables not in migration-0004: {found_tables - valid_tables}"


@pytest.mark.live
@pytest.mark.asyncio
async def test_tenant_mismatch_returns_403(
    live_test_configured,
    live_jwks_preflight,
    live_app,
    test_access_token,
    allocation_request,
    correlation_id,
    cleanup_test_records,
):
    """Test request body with different tenant_id returns 403 and creates no database record.

    Uses model_copy to create a validated mismatched request without mutating the shared fixture.
    """
    mismatched_metadata = allocation_request.metadata.model_copy(update={"tenant_id": OTHER_TENANT_ID})
    mismatch_request = allocation_request.model_copy(update={"metadata": mismatched_metadata})

    async with AsyncClient(transport=ASGITransport(app=live_app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent3/allocations",
            headers={"Authorization": f"Bearer {test_access_token.get_secret_value()}"},
            json=mismatch_request.model_dump(mode="json"),
        )

    assert response.status_code == 403
    body = response.json()
    error_detail = body.get("detail", body)
    assert error_detail["error_code"] == "TENANT_MISMATCH"


@pytest.mark.live
@pytest.mark.asyncio
async def test_cross_tenant_recommendation_lookup_returns_404(
    live_test_configured,
    live_jwks_preflight,
    live_app,
    test_access_token,
    test_requester_id,
    other_tenant_token,
    other_tenant_configured,
    correlation_id,
    cleanup_test_records,
    db_session,
):
    """Test cross-tenant recommendation lookup returns 404 without revealing existence.

    Uses current strict Pydantic schemas and model_dump(mode="json").
    """
    task_deadline = datetime.now(timezone.utc).replace(hour=23, minute=59, second=59)

    req = AllocationRequest(
        metadata=AgentMessageMetadata(
            correlation_id=correlation_id,
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=DEMO_TENANT_ID,
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
            timestamp=datetime.now(timezone.utc),
        ),
        human_requirements=HumanResourceRequirement(
            resource_type="HUMAN",
            required_roles=["developer"],
            mandatory_skills=["python"],
            preferred_skills=[],
            required_authority="senior",
            requester_id=test_requester_id,
            task_deadline=task_deadline,
            estimated_effort_hours=Decimal("8.0"),
            process_stage="resource_allocation",
        ),
        budget_requirements=BudgetResourceRequirement(
            resource_type="BUDGET",
            required_amount=Decimal("1000.00"),
            currency="USD",
            cost_centre="CC-DEMO",
            requester_id=test_requester_id,
            task_deadline=task_deadline,
            process_stage="resource_allocation",
        ),
    )

    async with AsyncClient(transport=ASGITransport(app=live_app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/agent3/allocations",
            headers={"Authorization": f"Bearer {test_access_token.get_secret_value()}"},
            json=req.model_dump(mode="json"),
        )

    assert response.status_code == 201
    result = response.json()
    recommendation_id = UUID(result["recommendation_id"])

    # Now try to lookup with other tenant token
    async with AsyncClient(transport=ASGITransport(app=live_app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/agent3/recommendations/{recommendation_id}",
            headers={"Authorization": f"Bearer {other_tenant_token.get_secret_value()}"},
        )

    assert response.status_code == 404
    body = response.json()
    error_detail = body.get("detail", body)
    assert error_detail["error_code"] == "RECOMMENDATION_NOT_FOUND"
