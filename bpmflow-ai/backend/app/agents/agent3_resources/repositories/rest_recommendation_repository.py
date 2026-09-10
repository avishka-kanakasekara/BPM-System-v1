"""Supabase REST persistence for Agent 3 recommendations when Postgres is down."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from app.core.supabase_rest import rest_insert, rest_select

from ..schemas import AllocationRecommendation, AllocationRequest


class RestRecommendationWriteRepository:
    """Persist allocation request + recommendation headers via PostgREST."""

    async def persist_allocation_result(
        self,
        request: AllocationRequest,
        recommendation: AllocationRecommendation,
        evaluation_timestamp: datetime,
    ) -> UUID:
        tenant_id = request.metadata.tenant_id
        correlation_id = request.metadata.correlation_id
        request_id = uuid4()
        recommendation_id = uuid4()
        requester_id = (
            (request.human_requirements.requester_id if request.human_requirements else None)
            or (request.budget_requirements.requester_id if request.budget_requirements else None)
            or request.metadata.task_id
        )
        idempotency_key = f"{correlation_id}:{request.metadata.task_id}"

        existing = rest_select(
            "allocation_requests",
            {
                "select": "id",
                "tenant_id": f"eq.{tenant_id}",
                "idempotency_key": f"eq.{idempotency_key}",
                "limit": "1",
            },
        )
        if existing:
            request_id = UUID(str(existing[0]["id"]))
            prior = rest_select(
                "allocation_recommendations",
                {
                    "select": "id",
                    "tenant_id": f"eq.{tenant_id}",
                    "request_id": f"eq.{request_id}",
                    "order": "recommendation_version.desc",
                    "limit": "1",
                },
            )
            if prior:
                return UUID(str(prior[0]["id"]))
        else:
            rest_insert(
                "allocation_requests",
                {
                    "id": str(request_id),
                    "tenant_id": str(tenant_id),
                    "idempotency_key": idempotency_key,
                    "correlation_id": str(correlation_id),
                    "requester_id": str(requester_id),
                    "evaluation_timestamp": evaluation_timestamp.astimezone(timezone.utc).isoformat(),
                    "process_instance_id": str(request.metadata.process_instance_id),
                    "task_id": str(request.metadata.task_id),
                    "request_payload": request.model_dump(mode="json"),
                    "request_schema_version": request.metadata.schema_version,
                },
            )

        status = (
            recommendation.status.value
            if hasattr(recommendation.status, "value")
            else str(recommendation.status)
        )
        confidence = getattr(recommendation, "confidence", None)
        rest_insert(
            "allocation_recommendations",
            {
                "id": str(recommendation_id),
                "tenant_id": str(tenant_id),
                "request_id": str(request_id),
                "correlation_id": str(correlation_id),
                "recommendation_version": 1,
                "status": status,
                "requires_human_approval": bool(
                    getattr(recommendation, "requires_human_approval", False)
                ),
                "manual_intervention_required": bool(
                    getattr(recommendation, "manual_intervention_required", False)
                ),
                "explanation": recommendation.explanation or "",
                "confidence": float(confidence) if confidence is not None else None,
                "error_code": getattr(recommendation, "error_code", None),
                "error_message": getattr(recommendation, "error_message", None),
                "response_schema_version": request.metadata.schema_version,
                "limitations": list(getattr(recommendation, "limitations", []) or []),
                "retryable": getattr(recommendation, "retryable", None),
            },
        )
        return recommendation_id

    async def get_recommendation(
        self,
        tenant_id: UUID,
        recommendation_id: UUID,
    ) -> Optional[dict[str, Any]]:
        rows = rest_select(
            "allocation_recommendations",
            {
                "select": "*",
                "tenant_id": f"eq.{tenant_id}",
                "id": f"eq.{recommendation_id}",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    async def get_latest_recommendation_by_correlation_id(
        self,
        tenant_id: UUID,
        correlation_id: UUID,
    ) -> Optional[dict[str, Any]]:
        rows = rest_select(
            "allocation_recommendations",
            {
                "select": "*",
                "tenant_id": f"eq.{tenant_id}",
                "correlation_id": f"eq.{correlation_id}",
                "order": "recommendation_version.desc",
                "limit": "1",
            },
        )
        return rows[0] if rows else None
