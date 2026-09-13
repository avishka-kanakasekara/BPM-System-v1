"""Company Policy & Knowledge Repository APIs for Agent 4 governance."""

from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.v1.deps import (
    get_policy_ingestion_service,
    get_policy_repository,
    get_policy_retrieval_service,
)
from app.core.security import get_current_user, require_roles
from app.policy_knowledge import (
    CompanyPolicyRecord,
    PolicyCategory,
    PolicyConflictError,
    PolicyCreateRequest,
    PolicyIngestionService,
    PolicyNotFoundError,
    PolicyRetrievalResult,
    PolicyRetrievalService,
    PolicyRule,
    PolicyVersionStatus,
)
from app.policy_knowledge.repository import PolicyRepository
from app.schemas.auth import CurrentUser

router = APIRouter(prefix="/policies", tags=["policies"])


def _require_tenant(user: CurrentUser) -> UUID:
    if user.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context is required for company policy operations",
        )
    return user.tenant_id


def _record_policy_audit(
    *,
    action: str,
    actor_id: UUID,
    tenant_id: UUID,
    entity_id: UUID,
    metadata: dict,
) -> None:
    """Best-effort audit for policy lifecycle events."""
    try:
        from uuid import uuid4 as _uuid4

        from app.core.supabase_rest import rest_insert, supabase_rest_configured

        if not supabase_rest_configured():
            return
        rest_insert(
            "audit_logs",
            {
                "id": str(_uuid4()),
                "entity_type": "policy",
                "entity_id": str(entity_id),
                "action": action,
                "performed_by": str(actor_id),
                "old_values": None,
                "new_values": {"tenant_id": str(tenant_id), **metadata},
            },
        )
    except Exception:
        return


def _parse_rules(raw: str | None) -> list[PolicyRule]:
    if not raw or not raw.strip():
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid rules JSON: {exc}",
        ) from exc
    if not isinstance(payload, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="rules must be a JSON array",
        )
    try:
        return [PolicyRule.model_validate(item) for item in payload]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid policy rule payload: {exc}",
        ) from exc


@router.post("", response_model=CompanyPolicyRecord, status_code=status.HTTP_201_CREATED)
async def upload_policy(
    name: str = Form(...),
    category: PolicyCategory = Form(...),
    version_label: str = Form(...),
    description: str | None = Form(None),
    document_type: str = Form("txt"),
    activate: bool = Form(True),
    access_scope: str = Form("tenant"),
    effective_from: datetime | None = Form(None),
    effective_to: datetime | None = Form(None),
    text_content: str | None = Form(None),
    rules: str | None = Form(None),
    file: UploadFile | None = File(None),
    current_user: CurrentUser = Depends(require_roles("admin")),
    ingestion: PolicyIngestionService = Depends(get_policy_ingestion_service),
) -> CompanyPolicyRecord:
    """Upload/create a tenant company policy version (admin only)."""
    tenant_id = _require_tenant(current_user)
    file_bytes = await file.read() if file is not None else None
    filename = file.filename if file is not None else None
    request = PolicyCreateRequest(
        name=name,
        category=category,
        version_label=version_label,
        description=description,
        document_type=document_type,
        activate=activate,
        access_scope=access_scope,
        effective_from=effective_from,
        effective_to=effective_to,
        text_content=text_content,
        rules=_parse_rules(rules),
    )
    try:
        record = await ingestion.ingest(
            tenant_id=tenant_id,
            request=request,
            uploaded_by=current_user.id,
            file_bytes=file_bytes,
            filename=filename,
        )
        _record_policy_audit(
            action="POLICY_UPLOADED",
            actor_id=current_user.id,
            tenant_id=tenant_id,
            entity_id=record.id,
            metadata={
                "name": record.name,
                "category": record.category.value,
                "version": request.version_label,
                "activated": request.activate,
            },
        )
        if request.activate:
            _record_policy_audit(
                action="POLICY_ACTIVATED",
                actor_id=current_user.id,
                tenant_id=tenant_id,
                entity_id=record.id,
                metadata={"version": request.version_label},
            )
        return record
    except PolicyConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("", response_model=list[CompanyPolicyRecord])
async def list_policies(
    current_user: CurrentUser = Depends(get_current_user),
    repository: PolicyRepository = Depends(get_policy_repository),
) -> list[CompanyPolicyRecord]:
    tenant_id = _require_tenant(current_user)
    return await repository.list_policies(tenant_id)


@router.get("/meta/categories", response_model=list[str])
async def list_policy_categories(
    current_user: CurrentUser = Depends(get_current_user),
) -> list[str]:
    _ = current_user
    return [c.value for c in PolicyCategory]


@router.get("/meta/statuses", response_model=list[str])
async def list_policy_statuses(
    current_user: CurrentUser = Depends(get_current_user),
) -> list[str]:
    _ = current_user
    return [s.value for s in PolicyVersionStatus]


@router.get("/search", response_model=PolicyRetrievalResult)
async def search_policies(
    q: str,
    category: PolicyCategory | None = None,
    current_user: CurrentUser = Depends(get_current_user),
    retrieval: PolicyRetrievalService = Depends(get_policy_retrieval_service),
) -> PolicyRetrievalResult:
    tenant_id = _require_tenant(current_user)
    categories = [category] if category is not None else None
    return await retrieval.search(tenant_id=tenant_id, query=q, categories=categories)


@router.get("/{policy_id}", response_model=CompanyPolicyRecord)
async def get_policy(
    policy_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    repository: PolicyRepository = Depends(get_policy_repository),
) -> CompanyPolicyRecord:
    tenant_id = _require_tenant(current_user)
    policy = await repository.get_policy(tenant_id, policy_id)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return policy


@router.post("/{policy_id}/versions/{version_id}/activate", response_model=CompanyPolicyRecord)
async def activate_policy_version(
    policy_id: UUID,
    version_id: UUID,
    current_user: CurrentUser = Depends(require_roles("admin")),
    repository: PolicyRepository = Depends(get_policy_repository),
) -> CompanyPolicyRecord:
    tenant_id = _require_tenant(current_user)
    try:
        record = await repository.activate_version(tenant_id, policy_id, version_id)
        _record_policy_audit(
            action="POLICY_ACTIVATED",
            actor_id=current_user.id,
            tenant_id=tenant_id,
            entity_id=policy_id,
            metadata={"version_id": str(version_id)},
        )
        return record
    except PolicyNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{policy_id}/versions/{version_id}/archive", response_model=CompanyPolicyRecord)
async def archive_policy_version(
    policy_id: UUID,
    version_id: UUID,
    current_user: CurrentUser = Depends(require_roles("admin")),
    repository: PolicyRepository = Depends(get_policy_repository),
) -> CompanyPolicyRecord:
    tenant_id = _require_tenant(current_user)
    try:
        record = await repository.archive_version(tenant_id, policy_id, version_id)
        _record_policy_audit(
            action="POLICY_ARCHIVED",
            actor_id=current_user.id,
            tenant_id=tenant_id,
            entity_id=policy_id,
            metadata={"version_id": str(version_id)},
        )
        return record
    except PolicyNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
