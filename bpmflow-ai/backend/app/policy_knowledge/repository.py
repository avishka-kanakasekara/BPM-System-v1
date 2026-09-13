"""In-memory and REST-backed persistence for company policies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from uuid import UUID

from .constants import PolicyCategory, PolicyVersionStatus
from .schemas import (
    CompanyPolicyRecord,
    PolicyChunk,
    PolicyCreateRequest,
    PolicyRule,
    PolicyVersionRecord,
)


class PolicyRepository(ABC):
    @abstractmethod
    async def create_policy_version(
        self,
        *,
        tenant_id: UUID,
        request: PolicyCreateRequest,
        chunks: list[PolicyChunk],
        rules: list[PolicyRule],
        uploaded_by: UUID | None,
        source_document_id: UUID | None,
        storage_path: str | None,
        document_name: str,
        document_type: str,
    ) -> CompanyPolicyRecord:
        raise NotImplementedError

    @abstractmethod
    async def list_policies(self, tenant_id: UUID) -> list[CompanyPolicyRecord]:
        raise NotImplementedError

    @abstractmethod
    async def get_policy(self, tenant_id: UUID, policy_id: UUID) -> CompanyPolicyRecord | None:
        raise NotImplementedError

    @abstractmethod
    async def activate_version(
        self, tenant_id: UUID, policy_id: UUID, version_id: UUID
    ) -> CompanyPolicyRecord:
        raise NotImplementedError

    @abstractmethod
    async def archive_version(
        self, tenant_id: UUID, policy_id: UUID, version_id: UUID
    ) -> CompanyPolicyRecord:
        raise NotImplementedError

    @abstractmethod
    async def list_active_versions(
        self,
        tenant_id: UUID,
        *,
        categories: list[PolicyCategory] | None = None,
        as_of: datetime | None = None,
    ) -> list[tuple[CompanyPolicyRecord, PolicyVersionRecord]]:
        raise NotImplementedError


class PolicyNotFoundError(Exception):
    pass


class PolicyConflictError(Exception):
    pass


class InMemoryPolicyRepository(PolicyRepository):
    """Unit-test / local policy store with strict tenant isolation."""

    def __init__(self) -> None:
        self._policies: dict[UUID, CompanyPolicyRecord] = {}

    def _owned(self, tenant_id: UUID, policy_id: UUID) -> CompanyPolicyRecord:
        policy = self._policies.get(policy_id)
        if policy is None or policy.tenant_id != tenant_id:
            raise PolicyNotFoundError(f"Policy {policy_id} not found for tenant")
        return policy

    async def create_policy_version(
        self,
        *,
        tenant_id: UUID,
        request: PolicyCreateRequest,
        chunks: list[PolicyChunk],
        rules: list[PolicyRule],
        uploaded_by: UUID | None,
        source_document_id: UUID | None,
        storage_path: str | None,
        document_name: str,
        document_type: str,
    ) -> CompanyPolicyRecord:
        now = datetime.now(UTC)
        existing = next(
            (
                p
                for p in self._policies.values()
                if p.tenant_id == tenant_id
                and p.name.lower() == request.name.lower()
                and p.category == request.category
            ),
            None,
        )
        if existing is None:
            existing = CompanyPolicyRecord(
                tenant_id=tenant_id,
                name=request.name,
                category=request.category,
                description=request.description,
                created_by=uploaded_by,
                created_at=now,
                updated_at=now,
            )
            self._policies[existing.id] = existing

        if any(v.version_label == request.version_label for v in existing.versions):
            raise PolicyConflictError(
                f"Version {request.version_label} already exists for policy {existing.name}"
            )

        status = (
            PolicyVersionStatus.ACTIVE
            if request.activate
            else PolicyVersionStatus.DRAFT
        )
        if status is PolicyVersionStatus.ACTIVE:
            for version in existing.versions:
                if version.status is PolicyVersionStatus.ACTIVE:
                    version.status = PolicyVersionStatus.ARCHIVED

        version = PolicyVersionRecord(
            policy_id=existing.id,
            tenant_id=tenant_id,
            version_label=request.version_label,
            status=status,
            document_name=document_name,
            document_type=document_type,
            source_document_id=source_document_id,
            storage_path=storage_path,
            effective_from=request.effective_from or now,
            effective_to=request.effective_to,
            uploaded_by=uploaded_by,
            uploaded_at=now,
            access_scope=request.access_scope,
            chunks=chunks,
            rules=rules,
        )
        existing.versions.append(version)
        existing.updated_at = now
        return existing.model_copy(deep=True)

    async def list_policies(self, tenant_id: UUID) -> list[CompanyPolicyRecord]:
        return [
            p.model_copy(deep=True)
            for p in self._policies.values()
            if p.tenant_id == tenant_id
        ]

    async def get_policy(self, tenant_id: UUID, policy_id: UUID) -> CompanyPolicyRecord | None:
        try:
            return self._owned(tenant_id, policy_id).model_copy(deep=True)
        except PolicyNotFoundError:
            return None

    async def activate_version(
        self, tenant_id: UUID, policy_id: UUID, version_id: UUID
    ) -> CompanyPolicyRecord:
        policy = self._owned(tenant_id, policy_id)
        target = next((v for v in policy.versions if v.id == version_id), None)
        if target is None:
            raise PolicyNotFoundError("Policy version not found")
        for version in policy.versions:
            if version.status is PolicyVersionStatus.ACTIVE:
                version.status = PolicyVersionStatus.ARCHIVED
        target.status = PolicyVersionStatus.ACTIVE
        policy.updated_at = datetime.now(UTC)
        return policy.model_copy(deep=True)

    async def archive_version(
        self, tenant_id: UUID, policy_id: UUID, version_id: UUID
    ) -> CompanyPolicyRecord:
        policy = self._owned(tenant_id, policy_id)
        target = next((v for v in policy.versions if v.id == version_id), None)
        if target is None:
            raise PolicyNotFoundError("Policy version not found")
        target.status = PolicyVersionStatus.ARCHIVED
        policy.updated_at = datetime.now(UTC)
        return policy.model_copy(deep=True)

    async def list_active_versions(
        self,
        tenant_id: UUID,
        *,
        categories: list[PolicyCategory] | None = None,
        as_of: datetime | None = None,
    ) -> list[tuple[CompanyPolicyRecord, PolicyVersionRecord]]:
        now = as_of or datetime.now(UTC)
        results: list[tuple[CompanyPolicyRecord, PolicyVersionRecord]] = []
        for policy in self._policies.values():
            if policy.tenant_id != tenant_id:
                continue
            if categories and policy.category not in categories:
                continue
            for version in policy.versions:
                if version.status is not PolicyVersionStatus.ACTIVE:
                    continue
                if version.effective_from > now:
                    continue
                if version.effective_to is not None and version.effective_to < now:
                    continue
                results.append((policy.model_copy(deep=True), version.model_copy(deep=True)))
        return results


# Singleton used by API deps when SQL/REST wiring is unavailable in tests/dev.
_DEFAULT_REPO = InMemoryPolicyRepository()


def get_default_policy_repository() -> InMemoryPolicyRepository:
    return _DEFAULT_REPO


def reset_default_policy_repository() -> InMemoryPolicyRepository:
    global _DEFAULT_REPO
    _DEFAULT_REPO = InMemoryPolicyRepository()
    return _DEFAULT_REPO
