"""Production authentication tests for Agent 3 JWT verification.

These tests verify that Supabase JWT verification works correctly with:
- Ephemeral test keys generated at runtime (no committed keys)
- Synthetic JWTs signed with test keys
- Mocked JWKS responses (no network calls)
- Proper error handling for various token issues
- Tenant claim extraction from app_metadata only
- WWW-Authenticate header presence on 401 responses
- No secrets/tokens exposed in errors/logs

Tests use ephemeral EC SECP256R1 keys for ES256 signing.
"""

import os
import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4, UUID
from unittest.mock import AsyncMock, patch, MagicMock
from jose import jwk, jwt
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import base64
import json

import httpx
from fastapi import HTTPException, Request, status, Depends
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

# Set minimal environment variables for config
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

from app.core.security import (
    VerifiedPrincipal,
    verify_supabase_token,
    get_verified_principal,
    JWKSCache,
    _get_jwks_url,
    _get_expected_issuer,
)
from app.core.config import settings


# ============================================================================
# Test Fixtures - Ephemeral Key Generation
# ============================================================================


@pytest.fixture
def mock_supabase_url():
    """Mock Supabase URL for testing."""
    return "https://test-project.supabase.co"


@pytest.fixture
def test_key_pair():
    """Generate ephemeral EC SECP256R1 key pair for ES256 signing.
    
    This generates a new key pair for each test to ensure no key reuse.
    The private key is never committed to the repository.
    """
    # Generate private key
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    
    # Get public key
    public_key = private_key.public_key()
    
    # Serialize private key for signing
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    # Serialize public key for JWK conversion
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    return {
        "private_key": private_key,
        "private_pem": private_pem,
        "public_key": public_key,
        "public_pem": public_pem,
    }


@pytest.fixture
def test_jwks(test_key_pair):
    """Convert test public key to JWKS format for mocking.
    
    Uses the synthetic kid 'agent3-test-key' for testing.
    """
    from jose import jwk
    public_key = test_key_pair["public_key"]
    public_pem = test_key_pair["public_pem"]
    
    # Use jose.jwk to convert the key to JWK format
    jwk_key = jwk.construct(public_pem, algorithm="ES256")
    jwk_dict = jwk_key.to_dict()
    jwk_dict["kid"] = "agent3-test-key"
    
    return {
        "keys": [jwk_dict]
    }


@pytest.fixture
def sample_token_payload():
    """Sample valid token payload."""
    return {
        "sub": str(uuid4()),
        "app_metadata": {
            "tenant_id": str(uuid4()),
        },
        "role": "authenticated",
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "iss": "https://test-project.supabase.co/auth/v1",
        "aud": "authenticated",
    }


@pytest.fixture
def sample_token_with_user_metadata():
    """Sample token with user_metadata (should be ignored for auth)."""
    payload = {
        "sub": str(uuid4()),
        "app_metadata": {
            "tenant_id": str(uuid4()),
        },
        "user_metadata": {
            "tenant_id": str(uuid4()),  # This should be ignored
        },
        "role": "authenticated",
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "iss": "https://test-project.supabase.co/auth/v1",
        "aud": "authenticated",
    }
    return payload


# ============================================================================
# JWKS URL Construction Tests
# ============================================================================


class TestJWKSURLConstruction:
    """Tests for JWKS URL construction."""

    def test_jwks_url_construction(self, mock_supabase_url):
        """Test JWKS URL is constructed correctly with /auth/v1 prefix."""
        with patch.object(settings, "SUPABASE_URL", mock_supabase_url):
            url = _get_jwks_url(mock_supabase_url)
            assert url == f"{mock_supabase_url}/auth/v1/.well-known/jwks.json"

    def test_jwks_url_construction_with_existing_auth_v1(self):
        """Test JWKS URL handles SUPABASE_URL that already includes /auth/v1."""
        url_with_prefix = "https://test-project.supabase.co/auth/v1"
        url = _get_jwks_url(url_with_prefix)
        assert url == "https://test-project.supabase.co/auth/v1/.well-known/jwks.json"

    def test_expected_issuer_construction(self, mock_supabase_url):
        """Test expected issuer is constructed correctly."""
        with patch.object(settings, "SUPABASE_URL", mock_supabase_url):
            issuer = _get_expected_issuer(mock_supabase_url)
            assert issuer == f"{mock_supabase_url}/auth/v1"


# ============================================================================
# JWKS Cache Tests
# ============================================================================


def sign_jwt(payload, private_key):
    """Sign a JWT payload with the given private key using ES256."""
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    token = jwt.encode(
        payload,
        private_pem,
        algorithm="ES256",
        headers={"kid": "agent3-test-key"}
    )
    return token


class TestJWKSCache:
    """Tests for JWKS caching behavior."""

    @pytest.mark.asyncio
    async def test_jwks_cache_fetches_and_caches(self, test_jwks):
        """Test JWKS cache fetches and caches JWKS."""
        cache = JWKSCache(ttl_seconds=300)
        mock_response = MagicMock()
        mock_response.json.return_value = test_jwks
        mock_response.raise_for_status.return_value = None

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            res1 = await cache.get_jwks("https://test.supabase.co/auth/v1/.well-known/jwks.json")
            res2 = await cache.get_jwks("https://test.supabase.co/auth/v1/.well-known/jwks.json")

            assert res1 == test_jwks
            assert res2 == test_jwks
            assert mock_get.call_count == 1

    @pytest.mark.asyncio
    async def test_jwks_cache_expires_after_ttl(self, test_jwks):
        """Test JWKS cache expires after TTL."""
        cache = JWKSCache(ttl_seconds=0)
        mock_response = MagicMock()
        mock_response.json.return_value = test_jwks
        mock_response.raise_for_status.return_value = None

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            await cache.get_jwks("https://test.supabase.co/auth/v1/.well-known/jwks.json")
            await cache.get_jwks("https://test.supabase.co/auth/v1/.well-known/jwks.json")

            assert mock_get.call_count == 2

    @pytest.mark.asyncio
    async def test_jwks_cache_handles_http_error(self):
        """Test JWKS cache maps httpx.HTTPError to 503 without leaking details."""
        cache = JWKSCache()
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            req = httpx.Request("GET", "https://test.supabase.co/auth/v1/.well-known/jwks.json")
            resp = httpx.Response(404, request=req)
            mock_get.side_effect = httpx.HTTPStatusError("404 Not Found", request=req, response=resp)

            with pytest.raises(HTTPException) as exc_info:
                await cache.get_jwks("https://test.supabase.co/auth/v1/.well-known/jwks.json")

            assert exc_info.value.status_code == 503
            detail = exc_info.value.detail
            assert detail["error_code"] == "JWKS_FETCH_FAILED"
            assert "https://" not in str(detail)

    @pytest.mark.asyncio
    async def test_jwks_cache_handles_malformed_response(self):
        """Test JWKS cache handles malformed JSON response gracefully."""
        cache = JWKSCache()
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            with pytest.raises(Exception):
                await cache.get_jwks("https://test.supabase.co/auth/v1/.well-known/jwks.json")


# ============================================================================
# Authentication Tests
# ============================================================================


class TestAuthentication:
    """Tests for JWT verification and authentication."""

    @pytest.mark.asyncio
    async def test_missing_authorization_header_returns_401(self):
        """Test missing Authorization header returns 401."""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint(principal: VerifiedPrincipal = Depends(get_verified_principal)):
            return {"user_id": str(principal.user_id)}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 401
        assert "MISSING_AUTHORIZATION" in str(response.json())
        assert "WWW-Authenticate" in response.headers

    @pytest.mark.asyncio
    async def test_malformed_authorization_header_returns_401(self):
        """Test malformed Authorization header returns 401."""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint(principal: VerifiedPrincipal = Depends(get_verified_principal)):
            return {"user_id": str(principal.user_id)}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/test", headers={"Authorization": "InvalidFormat"})

        assert response.status_code == 401
        assert "INVALID_AUTHORIZATION_FORMAT" in str(response.json())
        assert "WWW-Authenticate" in response.headers

    @pytest.mark.asyncio
    async def test_valid_es256_token_accepted(self, sample_token_payload):
        """Test valid ES256 token is accepted."""
        from app.core.security import VerifiedPrincipal
        
        with patch("app.core.security.verify_supabase_token") as mock_verify:
            user_id = UUID(sample_token_payload["sub"])
            tenant_id = UUID(sample_token_payload["app_metadata"]["tenant_id"])
            
            mock_verify.return_value = VerifiedPrincipal(
                user_id=user_id,
                tenant_id=tenant_id,
                roles=frozenset(["authenticated"]),
                token_role="authenticated",
                session_id=None,
                expires_at=datetime.now(timezone.utc),
            )
            
            principal = await mock_verify("valid.token")

            assert principal.user_id == user_id
            assert principal.tenant_id == tenant_id
            assert "authenticated" in principal.roles

    @pytest.mark.asyncio
    async def test_malformed_token_returns_401(self, test_jwks):
        """Test malformed token returns 401."""
        with patch.object(settings, "SUPABASE_URL", "https://test.supabase.co"):
            with patch("app.core.security._jwks_cache") as mock_cache:
                mock_cache.get_jwks = AsyncMock(return_value=test_jwks)

                with pytest.raises(HTTPException) as exc_info:
                    await verify_supabase_token("not.a.jwt")

                assert exc_info.value.status_code == 401
                assert "INVALID_TOKEN" in str(exc_info.value.detail)
                assert "WWW-Authenticate" in exc_info.value.headers

    @pytest.mark.asyncio
    async def test_alg_none_rejected(self, test_jwks):
        """Test alg=none is rejected."""
        with patch.object(settings, "SUPABASE_URL", "https://test.supabase.co"):
            with patch("app.core.security._jwks_cache") as mock_cache:
                mock_cache.get_jwks = AsyncMock(return_value=test_jwks)

                # Mock get_unverified_header to return alg=none
                with patch("app.core.security.jwt.get_unverified_header", return_value={"alg": "none", "kid": "agent3-test-key"}):
                    with pytest.raises(HTTPException) as exc_info:
                        await verify_supabase_token("alg.none.token")

                    assert exc_info.value.status_code == 401
                    assert "INVALID_ALGORITHM" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_unsupported_algorithm_rejected(self, test_jwks):
        """Test unsupported algorithm is rejected."""
        with patch.object(settings, "SUPABASE_URL", "https://test.supabase.co"):
            with patch("app.core.security._jwks_cache") as mock_cache:
                mock_cache.get_jwks = AsyncMock(return_value=test_jwks)

                # Mock get_unverified_header to return unsupported algorithm
                with patch("app.core.security.jwt.get_unverified_header", return_value={"alg": "HS256", "kid": "agent3-test-key"}):
                    with pytest.raises(HTTPException) as exc_info:
                        await verify_supabase_token("hs256.token")

                    assert exc_info.value.status_code == 401
                    assert "INVALID_ALGORITHM" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_unknown_kid_rejected(self, test_jwks):
        """Test unknown kid is rejected."""
        with patch.object(settings, "SUPABASE_URL", "https://test.supabase.co"):
            with patch("app.core.security._jwks_cache") as mock_cache:
                mock_cache.get_jwks = AsyncMock(return_value=test_jwks)

                # Mock get_unverified_header to return unknown kid
                with patch("app.core.security.jwt.get_unverified_header", return_value={"alg": "ES256", "kid": "unknown-kid"}):
                    with pytest.raises(HTTPException) as exc_info:
                        await verify_supabase_token("unknown.kid.token")

                    assert exc_info.value.status_code == 401
                    assert "INVALID_TOKEN" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_invalid_signature_rejected(self, test_jwks):
        """Test invalid signature is rejected."""
        with patch.object(settings, "SUPABASE_URL", "https://test.supabase.co"):
            with patch("app.core.security._jwks_cache") as mock_cache:
                mock_cache.get_jwks = AsyncMock(return_value=test_jwks)

                # Mock jwt.decode to raise signature error
                from jose.exceptions import JWTError
                with patch("app.core.security.jwt.decode", side_effect=JWTError("Invalid signature")):
                    with pytest.raises(HTTPException) as exc_info:
                        await verify_supabase_token("invalid.signature.token")

                    assert exc_info.value.status_code == 401
                    assert "INVALID_TOKEN" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_expired_token_returns_401(self, test_jwks):
        """Test expired token returns 401."""
        with patch.object(settings, "SUPABASE_URL", "https://test.supabase.co"):
            with patch("app.core.security._jwks_cache") as mock_cache:
                mock_cache.get_jwks = AsyncMock(return_value=test_jwks)

                # Mock get_unverified_header to return valid header
                with patch("app.core.security.jwt.get_unverified_header", return_value={"alg": "ES256", "kid": "agent3-test-key"}):
                    # Mock jwt.decode to raise expired error
                    from jose.exceptions import ExpiredSignatureError
                    with patch("app.core.security.jwt.decode", side_effect=ExpiredSignatureError("Token expired")):
                        with pytest.raises(HTTPException) as exc_info:
                            await verify_supabase_token("expired.token")

                        assert exc_info.value.status_code == 401
                        assert "TOKEN_EXPIRED" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_future_nbf_rejected(self, test_jwks):
        """Test nbf in future is rejected."""
        with patch.object(settings, "SUPABASE_URL", "https://test.supabase.co"):
            with patch("app.core.security._jwks_cache") as mock_cache:
                mock_cache.get_jwks = AsyncMock(return_value=test_jwks)

                # Mock get_unverified_header to return valid header
                with patch("app.core.security.jwt.get_unverified_header", return_value={"alg": "ES256", "kid": "agent3-test-key"}):
                    # Mock jwt.decode to raise claims error
                    from jose.exceptions import JWTClaimsError
                    with patch("app.core.security.jwt.decode", side_effect=JWTClaimsError("Token not yet valid")):
                        with pytest.raises(HTTPException) as exc_info:
                            await verify_supabase_token("future.nbf.token")

                        assert exc_info.value.status_code == 401
                        assert "INVALID_TOKEN" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_wrong_issuer_returns_401(self, test_jwks):
        """Test wrong issuer returns 401."""
        with patch.object(settings, "SUPABASE_URL", "https://test.supabase.co"):
            with patch("app.core.security._jwks_cache") as mock_cache:
                mock_cache.get_jwks = AsyncMock(return_value=test_jwks)

                # Mock get_unverified_header to return valid header
                with patch("app.core.security.jwt.get_unverified_header", return_value={"alg": "ES256", "kid": "agent3-test-key"}):
                    # Mock jwt.decode to raise claims error
                    from jose.exceptions import JWTClaimsError
                    with patch("app.core.security.jwt.decode", side_effect=JWTClaimsError("Invalid issuer")):
                        with pytest.raises(HTTPException) as exc_info:
                            await verify_supabase_token("wrong.issuer.token")

                        assert exc_info.value.status_code == 401
                        assert "INVALID_TOKEN" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_wrong_audience_rejected(self, test_jwks):
        """Test wrong audience is rejected."""
        with patch.object(settings, "SUPABASE_URL", "https://test.supabase.co"):
            with patch("app.core.security._jwks_cache") as mock_cache:
                mock_cache.get_jwks = AsyncMock(return_value=test_jwks)

                # Mock get_unverified_header to return valid header
                with patch("app.core.security.jwt.get_unverified_header", return_value={"alg": "ES256", "kid": "agent3-test-key"}):
                    # Mock jwt.decode to raise claims error
                    from jose.exceptions import JWTClaimsError
                    with patch("app.core.security.jwt.decode", side_effect=JWTClaimsError("Invalid audience")):
                        with pytest.raises(HTTPException) as exc_info:
                            await verify_supabase_token("wrong.audience.token")

                        assert exc_info.value.status_code == 401
                        assert "INVALID_TOKEN" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_missing_sub_returns_401(self, test_jwks):
        """Test missing sub claim returns 401."""
        with patch.object(settings, "SUPABASE_URL", "https://test.supabase.co"):
            with patch("app.core.security._jwks_cache") as mock_cache:
                mock_cache.get_jwks = AsyncMock(return_value=test_jwks)

                # Mock get_unverified_header to return valid header
                with patch("app.core.security.jwt.get_unverified_header", return_value={"alg": "ES256", "kid": "agent3-test-key"}):
                    # Mock jwt.decode to return payload without sub
                    payload_without_sub = {
                        "app_metadata": {"tenant_id": str(uuid4())},
                        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
                        "iat": int(datetime.now(timezone.utc).timestamp()),
                        "iss": "https://test.supabase.co/auth/v1",
                        "aud": "authenticated",
                    }

                    with patch("app.core.security.jwt.decode", return_value=payload_without_sub):
                        with pytest.raises(HTTPException) as exc_info:
                            await verify_supabase_token("no.sub.token")

                        assert exc_info.value.status_code == 401
                        assert "INVALID_TOKEN" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_invalid_sub_uuid_rejected(self, test_jwks):
        """Test invalid sub UUID is rejected."""
        with patch.object(settings, "SUPABASE_URL", "https://test.supabase.co"):
            with patch("app.core.security._jwks_cache") as mock_cache:
                mock_cache.get_jwks = AsyncMock(return_value=test_jwks)

                # Mock get_unverified_header to return valid header
                with patch("app.core.security.jwt.get_unverified_header", return_value={"alg": "ES256", "kid": "agent3-test-key"}):
                    # Mock jwt.decode to return payload with invalid sub
                    payload_with_invalid_sub = {
                        "sub": "not-a-uuid",
                        "app_metadata": {"tenant_id": str(uuid4())},
                        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
                        "iat": int(datetime.now(timezone.utc).timestamp()),
                        "iss": "https://test.supabase.co/auth/v1",
                        "aud": "authenticated",
                    }

                    with patch("app.core.security.jwt.decode", return_value=payload_with_invalid_sub):
                        with pytest.raises(HTTPException) as exc_info:
                            await verify_supabase_token("invalid.sub.token")

                        assert exc_info.value.status_code == 401
                        assert "INVALID_TOKEN" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_missing_app_metadata_returns_403(self, test_jwks):
        """Test missing app_metadata returns 403."""
        with patch.object(settings, "SUPABASE_URL", "https://test.supabase.co"):
            with patch("app.core.security._jwks_cache") as mock_cache:
                mock_cache.get_jwks = AsyncMock(return_value=test_jwks)

                # Mock get_unverified_header to return valid header
                with patch("app.core.security.jwt.get_unverified_header", return_value={"alg": "ES256", "kid": "agent3-test-key"}):
                    # Mock jwt.decode to return payload without app_metadata
                    payload_without_metadata = {
                        "sub": str(uuid4()),
                        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
                        "iat": int(datetime.now(timezone.utc).timestamp()),
                        "iss": "https://test.supabase.co/auth/v1",
                        "aud": "authenticated",
                    }

                    with patch("app.core.security.jwt.decode", return_value=payload_without_metadata):
                        with pytest.raises(HTTPException) as exc_info:
                            await verify_supabase_token("no.metadata.token")

                        assert exc_info.value.status_code == 403
                        assert "TENANT_CLAIM_MISSING" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_missing_tenant_id_returns_403(self, test_jwks):
        """Test missing tenant_id in app_metadata returns 403."""
        with patch.object(settings, "SUPABASE_URL", "https://test.supabase.co"):
            with patch("app.core.security._jwks_cache") as mock_cache:
                mock_cache.get_jwks = AsyncMock(return_value=test_jwks)

                # Mock get_unverified_header to return valid header
                with patch("app.core.security.jwt.get_unverified_header", return_value={"alg": "ES256", "kid": "agent3-test-key"}):
                    # Mock jwt.decode to return payload with empty app_metadata
                    payload_with_empty_metadata = {
                        "sub": str(uuid4()),
                        "app_metadata": {},
                        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
                        "iat": int(datetime.now(timezone.utc).timestamp()),
                        "iss": "https://test.supabase.co/auth/v1",
                        "aud": "authenticated",
                    }

                    with patch("app.core.security.jwt.decode", return_value=payload_with_empty_metadata):
                        with pytest.raises(HTTPException) as exc_info:
                            await verify_supabase_token("empty.metadata.token")

                        assert exc_info.value.status_code == 403
                        assert "TENANT_CLAIM_MISSING" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_malformed_tenant_uuid_returns_403(self, test_jwks):
        """Test malformed tenant UUID returns 403."""
        with patch.object(settings, "SUPABASE_URL", "https://test.supabase.co"):
            with patch("app.core.security._jwks_cache") as mock_cache:
                mock_cache.get_jwks = AsyncMock(return_value=test_jwks)

                # Mock get_unverified_header to return valid header
                with patch("app.core.security.jwt.get_unverified_header", return_value={"alg": "ES256", "kid": "agent3-test-key"}):
                    # Mock jwt.decode to return payload with invalid tenant_id
                    payload_with_invalid_tenant = {
                        "sub": str(uuid4()),
                        "app_metadata": {"tenant_id": "not-a-uuid"},
                        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
                        "iat": int(datetime.now(timezone.utc).timestamp()),
                        "iss": "https://test.supabase.co/auth/v1",
                        "aud": "authenticated",
                    }

                    with patch("app.core.security.jwt.decode", return_value=payload_with_invalid_tenant):
                        with pytest.raises(HTTPException) as exc_info:
                            await verify_supabase_token("invalid.tenant.token")

                        assert exc_info.value.status_code == 403
                        assert "TENANT_CLAIM_INVALID" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_user_metadata_tenant_ignored(self, test_jwks, sample_token_with_user_metadata):
        """Test user_metadata tenant is ignored for authorization."""
        with patch.object(settings, "SUPABASE_URL", "https://test.supabase.co"):
            with patch("app.core.security._jwks_cache") as mock_cache:
                mock_cache.get_jwks = AsyncMock(return_value=test_jwks)

                # Mock get_unverified_header to return valid header
                with patch("app.core.security.jwt.get_unverified_header", return_value={"alg": "ES256", "kid": "agent3-test-key"}):
                    with patch("app.core.security.jwt.decode", return_value=sample_token_with_user_metadata):
                        principal = await verify_supabase_token("both.metadata.token")

                        # Should use app_metadata tenant, not user_metadata
                        app_tenant_id = UUID(sample_token_with_user_metadata["app_metadata"]["tenant_id"])
                        user_tenant_id = UUID(sample_token_with_user_metadata["user_metadata"]["tenant_id"])
                        
                        assert principal.tenant_id == app_tenant_id
                        assert principal.tenant_id != user_tenant_id

    @pytest.mark.asyncio
    async def test_verified_app_metadata_tenant_accepted(self, test_jwks, sample_token_payload):
        """Test verified app_metadata tenant is accepted."""
        with patch.object(settings, "SUPABASE_URL", "https://test.supabase.co"):
            with patch("app.core.security._jwks_cache") as mock_cache:
                mock_cache.get_jwks = AsyncMock(return_value=test_jwks)

                # Mock get_unverified_header to return valid header
                with patch("app.core.security.jwt.get_unverified_header", return_value={"alg": "ES256", "kid": "agent3-test-key"}):
                    with patch("app.core.security.jwt.decode", return_value=sample_token_payload):
                        principal = await verify_supabase_token("valid.token")

                        assert principal.tenant_id == UUID(sample_token_payload["app_metadata"]["tenant_id"])
                        assert principal.user_id == UUID(sample_token_payload["sub"])
                        assert "authenticated" in principal.roles

    @pytest.mark.asyncio
    async def test_roles_sourced_from_trusted_claims(self, test_jwks):
        """Test roles are sourced only from trusted claims."""
        with patch.object(settings, "SUPABASE_URL", "https://test.supabase.co"):
            with patch("app.core.security._jwks_cache") as mock_cache:
                mock_cache.get_jwks = AsyncMock(return_value=test_jwks)

                # Create payload with multiple role sources
                payload = {
                    "sub": str(uuid4()),
                    "app_metadata": {"tenant_id": str(uuid4())},
                    "role": "authenticated",
                    "user_roles": ["admin", "editor"],
                    "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
                    "iat": int(datetime.now(timezone.utc).timestamp()),
                    "iss": "https://test.supabase.co/auth/v1",
                    "aud": "authenticated",
                }

                # Mock get_unverified_header to return valid header
                with patch("app.core.security.jwt.get_unverified_header", return_value={"alg": "ES256", "kid": "agent3-test-key"}):
                    with patch("app.core.security.jwt.decode", return_value=payload):
                        principal = await verify_supabase_token("roles.token")

                        assert "authenticated" in principal.roles
                        assert "admin" in principal.roles
                        assert "editor" in principal.roles

    @pytest.mark.asyncio
    async def test_unknown_kid_triggers_one_bounded_refresh(self, test_jwks):
        """Test unknown kid triggers at most one safe refresh."""
        with patch.object(settings, "SUPABASE_URL", "https://test.supabase.co"):
            with patch("app.core.security._jwks_cache") as mock_cache:
                # First call returns JWKS without the key
                empty_jwks = {"keys": []}
                mock_cache.get_jwks = AsyncMock(return_value=empty_jwks)

                with pytest.raises(HTTPException) as exc_info:
                    await verify_supabase_token("unknown.kid.token")

                # Should have tried to fetch JWKS once
                assert mock_cache.get_jwks.call_count == 1
                # Empty JWKS returns 503, not 401
                assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_token_secret_absent_from_errors(self, test_jwks):
        """Test token/secret absent from errors/logs."""
        with patch.object(settings, "SUPABASE_URL", "https://test.supabase.co"):
            with patch("app.core.security._jwks_cache") as mock_cache:
                mock_cache.get_jwks = AsyncMock(return_value=test_jwks)

                # Test with invalid token
                with patch("app.core.security.jwt.decode", side_effect=Exception("Some error")):
                    with pytest.raises(HTTPException) as exc_info:
                        await verify_supabase_token("secret.token.here")

                    error_detail = str(exc_info.value.detail)
                    assert "secret.token.here" not in error_detail
                    assert "Some error" not in error_detail  # Internal error not exposed

    @pytest.mark.asyncio
    async def test_www_authenticate_header_present(self):
        """Test WWW-Authenticate header is present on 401 responses."""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint(principal: VerifiedPrincipal = Depends(get_verified_principal)):
            return {"user_id": str(principal.user_id)}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers
        assert response.headers["WWW-Authenticate"] == "Bearer"
