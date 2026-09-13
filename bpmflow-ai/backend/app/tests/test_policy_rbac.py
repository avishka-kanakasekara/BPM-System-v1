"""RBAC tests for company policy APIs + auth/me role exposure."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.v1.deps import (
    get_policy_ingestion_service,
    get_policy_repository,
    get_policy_retrieval_service,
)
from app.core.security import get_current_user
from app.main import app
from app.policy_knowledge import (
    PolicyIngestionService,
    PolicyRetrievalService,
    reset_default_policy_repository,
)
from app.tests.auth_helpers import override_current_user

FORBIDDEN_DETAIL = "Insufficient permissions"


@pytest.fixture
def policy_api():
    repo = reset_default_policy_repository()
    ingestion = PolicyIngestionService(repo)
    retrieval = PolicyRetrievalService(repo)

    async def _repo():
        return repo

    async def _ingestion():
        return ingestion

    async def _retrieval():
        return retrieval

    app.dependency_overrides[get_policy_repository] = _repo
    app.dependency_overrides[get_policy_ingestion_service] = _ingestion
    app.dependency_overrides[get_policy_retrieval_service] = _retrieval

    client = TestClient(app)
    yield client, repo
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_policy_repository, None)
    app.dependency_overrides.pop(get_policy_ingestion_service, None)
    app.dependency_overrides.pop(get_policy_retrieval_service, None)


def _upload_form(**overrides):
    data = {
        "name": "Procurement Policy",
        "category": "PROCUREMENT",
        "version_label": "2026.1",
        "activate": "true",
        "document_type": "txt",
        "text_content": (
            "Purchases above 1000000 LKR require Senior Management approval.\n"
            "A quotation is required."
        ),
    }
    data.update(overrides)
    return data


class TestPolicyRoleAuthorization:
    def test_unauthenticated_policy_upload_rejected(self, policy_api) -> None:
        client, _ = policy_api
        # No override => get_current_user runs real auth and fails without bearer.
        response = client.post("/api/v1/policies", data=_upload_form())
        assert response.status_code in (401, 403)

    def test_requester_cannot_upload_policy(self, policy_api) -> None:
        client, _ = policy_api
        tenant = uuid4()
        override_current_user(role="requester", tenant_id=tenant)
        response = client.post("/api/v1/policies", data=_upload_form())
        assert response.status_code == 403
        assert response.json()["detail"] == FORBIDDEN_DETAIL

    def test_approver_cannot_upload_policy(self, policy_api) -> None:
        client, _ = policy_api
        tenant = uuid4()
        override_current_user(role="approver", tenant_id=tenant)
        response = client.post("/api/v1/policies", data=_upload_form())
        assert response.status_code == 403

    def test_admin_can_upload_and_list_policy(self, policy_api) -> None:
        client, _ = policy_api
        tenant = uuid4()
        override_current_user(role="admin", tenant_id=tenant)
        created = client.post("/api/v1/policies", data=_upload_form())
        assert created.status_code == 201
        body = created.json()
        assert body["category"] == "PROCUREMENT"
        assert body["versions"][0]["status"] == "ACTIVE"

        listed = client.get("/api/v1/policies")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

    def test_requester_cannot_activate_or_archive(self, policy_api) -> None:
        client, _ = policy_api
        tenant = uuid4()
        override_current_user(role="admin", tenant_id=tenant)
        created = client.post("/api/v1/policies", data=_upload_form()).json()
        policy_id = created["id"]
        version_id = created["versions"][0]["id"]

        override_current_user(role="requester", tenant_id=tenant)
        activate = client.post(f"/api/v1/policies/{policy_id}/versions/{version_id}/activate")
        archive = client.post(f"/api/v1/policies/{policy_id}/versions/{version_id}/archive")
        assert activate.status_code == 403
        assert archive.status_code == 403

    def test_admin_can_archive_and_activate(self, policy_api) -> None:
        client, _ = policy_api
        tenant = uuid4()
        override_current_user(role="admin", tenant_id=tenant)
        first = client.post("/api/v1/policies", data=_upload_form(version_label="2025.1")).json()
        second = client.post(
            "/api/v1/policies",
            data=_upload_form(version_label="2026.1"),
        ).json()
        policy_id = second["id"]
        assert policy_id == first["id"]
        old_version = next(v for v in second["versions"] if v["version_label"] == "2025.1")
        # Reactivate archived 2025 after uploading 2026
        archived = client.post(
            f"/api/v1/policies/{policy_id}/versions/{old_version['id']}/archive"
        )
        assert archived.status_code == 200
        activated = client.post(
            f"/api/v1/policies/{policy_id}/versions/{old_version['id']}/activate"
        )
        assert activated.status_code == 200
        statuses = {v["version_label"]: v["status"] for v in activated.json()["versions"]}
        assert statuses["2025.1"] == "ACTIVE"

    def test_tenant_isolation_on_list(self, policy_api) -> None:
        client, _ = policy_api
        tenant_a = uuid4()
        tenant_b = uuid4()
        override_current_user(role="admin", tenant_id=tenant_a)
        assert client.post("/api/v1/policies", data=_upload_form()).status_code == 201

        override_current_user(role="admin", tenant_id=tenant_b)
        listed = client.get("/api/v1/policies")
        assert listed.status_code == 200
        assert listed.json() == []

    def test_tenant_b_cannot_activate_tenant_a_policy(self, policy_api) -> None:
        client, _ = policy_api
        tenant_a = uuid4()
        tenant_b = uuid4()
        override_current_user(role="admin", tenant_id=tenant_a)
        created = client.post("/api/v1/policies", data=_upload_form()).json()
        policy_id = created["id"]
        version_id = created["versions"][0]["id"]

        override_current_user(role="admin", tenant_id=tenant_b)
        response = client.post(
            f"/api/v1/policies/{policy_id}/versions/{version_id}/activate"
        )
        assert response.status_code == 404

    def test_auth_me_exposes_role(self, policy_api) -> None:
        client, _ = policy_api
        tenant = uuid4()
        uid = override_current_user(role="admin", tenant_id=tenant, email="admin@example.com")
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(uid)
        assert body["role"] == "admin"
        assert body["tenant_id"] == str(tenant)
        assert body["email"] == "admin@example.com"

    def test_register_schema_accepts_allowed_roles(self) -> None:
        """Development register accepts requester/approver/admin only."""
        from pydantic import ValidationError

        from app.schemas.auth import AuthRegisterRequest

        for role in ("requester", "approver", "admin"):
            parsed = AuthRegisterRequest.model_validate(
                {
                    "email": "user@example.com",
                    "password": "password123",
                    "role": role,
                }
            )
            assert parsed.role == role

        with pytest.raises(ValidationError):
            AuthRegisterRequest.model_validate(
                {
                    "email": "user@example.com",
                    "password": "password123",
                    "role": "superadmin",
                }
            )

    def test_missing_tenant_blocks_policy_ops(self, policy_api) -> None:
        client, _ = policy_api
        override_current_user(role="admin", tenant_id=None)
        response = client.post("/api/v1/policies", data=_upload_form())
        assert response.status_code == 403
        assert "Tenant context" in response.json()["detail"]
