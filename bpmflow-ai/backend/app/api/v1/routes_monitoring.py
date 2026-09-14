"""Process monitoring, KPI, bottleneck, and TO-BE recommendation APIs."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.v1.deps import get_policy_retrieval_service
from app.core.security import get_current_user, require_roles
from app.monitoring.recommendations import (
    ProcessMissingError,
    RecommendationNotFoundError,
    RecommendationNotReviewableError,
    RecommendationReviewForbiddenError,
    TobeRecommendationService,
)
from app.monitoring.schemas import (
    KpiReport,
    ProcessMonitoringReport,
    RecommendationReviewRequest,
    TobeRecommendationRecord,
    TimelineEvent,
)
from app.monitoring.service import MonitoringService, ProcessMonitoringNotFoundError
from app.policy_knowledge.retrieval import PolicyRetrievalService
from app.schemas.auth import CurrentUser

router = APIRouter(tags=["monitoring"])


def _tenant(user: CurrentUser) -> UUID:
    if user.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="TENANT_REQUIRED")
    return user.tenant_id


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Process not found")


def _cross_tenant() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CROSS_TENANT_DENIED")


def get_monitoring_service() -> MonitoringService:
    return MonitoringService()


def get_tobe_service(
    policy_retrieval: PolicyRetrievalService = Depends(get_policy_retrieval_service),
) -> TobeRecommendationService:
    return TobeRecommendationService(policy_retrieval=policy_retrieval)


@router.get("/processes/{process_id}/monitoring", response_model=ProcessMonitoringReport)
async def get_process_monitoring(
    process_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
) -> ProcessMonitoringReport:
    tenant_id = _tenant(current_user)
    try:
        return service.report(tenant_id, process_id)
    except ProcessMonitoringNotFoundError as exc:
        raise _not_found() from exc


@router.get("/processes/{process_id}/timeline", response_model=list[TimelineEvent])
async def get_process_timeline(
    process_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
) -> list[TimelineEvent]:
    tenant_id = _tenant(current_user)
    try:
        return service.timeline(tenant_id, process_id)
    except ProcessMonitoringNotFoundError as exc:
        raise _not_found() from exc


@router.get("/processes/{process_id}/kpis", response_model=KpiReport)
async def get_process_kpis(
    process_id: UUID,
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
) -> KpiReport:
    tenant_id = _tenant(current_user)
    try:
        service.require_process(tenant_id, process_id)
    except ProcessMonitoringNotFoundError as exc:
        raise _not_found() from exc
    return service.kpis(tenant_id, process_id=process_id, window_start=start_date, window_end=end_date)


@router.post("/processes/{process_id}/kpis/calculate", response_model=KpiReport)
async def calculate_process_kpis(
    process_id: UUID,
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
) -> KpiReport:
    tenant_id = _tenant(current_user)
    try:
        before = service.require_process(tenant_id, process_id)
        stage = before.current_stage
        report = service.kpis(
            tenant_id, process_id=process_id, window_start=start_date, window_end=end_date
        )
        after = service.require_process(tenant_id, process_id)
        if after.current_stage != stage:
            raise HTTPException(status_code=500, detail="MONITORING_MUTATED_STATE")
        return report
    except ProcessMonitoringNotFoundError as exc:
        raise _not_found() from exc


@router.get("/processes/{process_id}/bottlenecks")
async def get_process_bottlenecks(
    process_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
):
    tenant_id = _tenant(current_user)
    try:
        service.require_process(tenant_id, process_id)
    except ProcessMonitoringNotFoundError as exc:
        raise _not_found() from exc
    return service.bottlenecks(tenant_id, process_id)


@router.get("/processes/{process_id}/exception-analytics")
async def get_process_exception_analytics(
    process_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
):
    tenant_id = _tenant(current_user)
    try:
        service.require_process(tenant_id, process_id)
    except ProcessMonitoringNotFoundError as exc:
        raise _not_found() from exc
    return service.exception_analytics(tenant_id, process_id)


@router.get("/processes/{process_id}/recommendations", response_model=list[TobeRecommendationRecord])
async def list_process_recommendations(
    process_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: TobeRecommendationService = Depends(get_tobe_service),
) -> list[TobeRecommendationRecord]:
    return service.list(_tenant(current_user), process_id)


@router.post("/processes/{process_id}/recommendations/generate", response_model=list[TobeRecommendationRecord])
async def generate_process_recommendations(
    process_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: TobeRecommendationService = Depends(get_tobe_service),
) -> list[TobeRecommendationRecord]:
    try:
        return await service.generate(_tenant(current_user), process_id)
    except ProcessMissingError as exc:
        raise _not_found() from exc


@router.get("/recommendations/{recommendation_id}", response_model=TobeRecommendationRecord)
async def get_recommendation(
    recommendation_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: TobeRecommendationService = Depends(get_tobe_service),
) -> TobeRecommendationRecord:
    try:
        return service.get(_tenant(current_user), recommendation_id)
    except RecommendationNotFoundError as exc:
        raise _cross_tenant() from exc


@router.post("/recommendations/{recommendation_id}/review", response_model=TobeRecommendationRecord)
async def review_recommendation(
    recommendation_id: UUID,
    payload: RecommendationReviewRequest,
    current_user: CurrentUser = Depends(require_roles("approver", "admin")),
    service: TobeRecommendationService = Depends(get_tobe_service),
) -> TobeRecommendationRecord:
    try:
        return service.review(
            _tenant(current_user),
            recommendation_id,
            decision=payload.decision,
            reviewer_id=current_user.id,
            role=current_user.role,
        )
    except RecommendationNotFoundError as exc:
        raise _cross_tenant() from exc
    except RecommendationReviewForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="INSUFFICIENT_ROLE") from exc
    except RecommendationNotReviewableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="NOT_REVIEWABLE") from exc
