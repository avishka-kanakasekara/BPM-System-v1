"""PostgreSQL write repository for Agent 3 recommendation persistence."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import text

from ..schemas import (
    AllocationRequest,
    AllocationRecommendation,
    HumanResourceRequirement,
    BudgetResourceRequirement,
    RequirementResult,
    RankedCandidate,
    ExcludedResource,
    ResourceGap,
    ResourceAlternative,
    BudgetValidationChecks,
    RecommendationStatus,
)
from .persistence_exceptions import (
    PersistenceError,
    PersistenceValidationError,
    PersistenceConflictError,
    PersistenceLookupError,
    PersistenceTransactionError,
)
from .write_mappers import (
    map_request_to_allocation_request,
    map_requirement_to_allocation_requirement,
    map_recommendation_to_allocation_recommendation,
    map_candidate_to_allocation_candidate,
    map_exclusion_to_allocation_exclusion,
    map_exclusion_reason_to_allocation_exclusion_reason,
    map_gap_to_resource_gap,
    map_alternative_to_resource_alternative,
    map_budget_validation_to_budget_validation_result,
    map_evidence_link_to_recommendation_evidence_link,
    validate_timezone_aware,
)
from .write_table_mapping import (
    SQL_SELECT_REQUEST_BY_IDEMPOTENCY,
    SQL_SELECT_RECOMMENDATION_ID_BY_REQUEST,
    SQL_SELECT_NEXT_RECOMMENDATION_VERSION,
    SQL_INSERT_ALLOCATION_REQUEST,
    SQL_INSERT_ALLOCATION_REQUIREMENT,
    SQL_INSERT_ALLOCATION_RECOMMENDATION,
    SQL_INSERT_ALLOCATION_CANDIDATE,
    SQL_INSERT_ALLOCATION_EXCLUSION,
    SQL_INSERT_ALLOCATION_EXCLUSION_REASON,
    SQL_INSERT_RESOURCE_GAP,
    SQL_INSERT_RESOURCE_ALTERNATIVE,
    SQL_INSERT_BUDGET_VALIDATION,
    SQL_INSERT_EVIDENCE_LINK,
    SQL_MARK_SUPERSEDED,
    SQL_SELECT_RECOMMENDATION_HEADER,
    SQL_SELECT_LATEST_RECOMMENDATION_HEADER,
    SQL_SELECT_REQUEST_METADATA,
    SQL_SELECT_REQUIREMENTS,
    SQL_SELECT_CANDIDATES,
    SQL_SELECT_EXCLUSIONS,
    SQL_SELECT_GAPS,
    SQL_SELECT_ALTERNATIVES,
    SQL_SELECT_BUDGET_VALIDATIONS,
    SQL_SELECT_EVIDENCE_LINKS,
)


class RecommendationWriteRepository:
    """PostgreSQL write repository for Agent 3 recommendations."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        """Initialize with an async session factory."""
        self._session_factory = session_factory

    @asynccontextmanager
    async def _transaction(self):
        """Context manager for database transactions with rollback on error."""
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except (PersistenceValidationError, PersistenceConflictError, PersistenceLookupError):
                # Re-raise persistence errors without wrapping
                await session.rollback()
                raise
            except Exception as exc:
                await session.rollback()
                raise PersistenceTransactionError(f"Transaction failed: {exc}") from exc

    async def persist_allocation_result(
        self,
        request: AllocationRequest,
        recommendation: AllocationRecommendation,
        evaluation_timestamp: datetime,
    ) -> UUID:
        """Persist a complete allocation result atomically.

        Args:
            request: The allocation request
            recommendation: The allocation recommendation
            evaluation_timestamp: The evaluation timestamp

        Returns:
            The recommendation_id

        Raises:
            PersistenceValidationError: If validation fails
            PersistenceTransactionError: If transaction fails
            PersistenceConflictError: If idempotency conflict
        """
        validate_timezone_aware(evaluation_timestamp, "evaluation_timestamp")

        async with self._transaction() as session:
            # Check for idempotency
            request_row = await self._check_idempotency(
                session,
                request.metadata.tenant_id,
                request.metadata.correlation_id,
            )
            if request_row:
                # Request already exists, check for existing recommendation
                existing_rec_id = await self._get_existing_recommendation(
                    session,
                    request.metadata.tenant_id,
                    request_row["id"],
                )
                if existing_rec_id:
                    raise PersistenceConflictError(
                        f"Recommendation already exists for correlation_id {request.metadata.correlation_id}"
                    )
                request_id = request_row["id"]
            else:
                # Insert new request
                request_id = await self._insert_request(
                    session,
                    request,
                    evaluation_timestamp,
                )

            # Get next recommendation version
            version = await self._get_next_version(
                session,
                request.metadata.tenant_id,
                request.metadata.correlation_id,
            )

            # Insert recommendation
            recommendation_id = await self._insert_recommendation(
                session,
                recommendation,
                request_id,
                request.metadata.tenant_id,
                version,
            )

            # Mark previous recommendations as superseded
            await self._mark_superseded(
                session,
                request.metadata.tenant_id,
                request.metadata.correlation_id,
                recommendation_id,
            )

            # Insert requirements
            requirement_ids = {}
            sequence = 1
            if request.human_requirements:
                human_req_id = await self._insert_requirement(
                    session,
                    request.human_requirements,
                    request_id,
                    request.metadata.tenant_id,
                    sequence,
                )
                requirement_ids["human"] = human_req_id
                sequence += 1

            if request.budget_requirements:
                budget_req_id = await self._insert_requirement(
                    session,
                    request.budget_requirements,
                    request_id,
                    request.metadata.tenant_id,
                    sequence,
                )
                requirement_ids["budget"] = budget_req_id

            # Insert candidates (only for business recommendations)
            if recommendation.human_requirement_result:
                await self._insert_candidates(
                    session,
                    recommendation.human_requirement_result.eligible_candidates,
                    recommendation_id,
                    request_id,
                    requirement_ids.get("human"),
                    request.metadata.tenant_id,
                )

                await self._insert_exclusions(
                    session,
                    recommendation.human_requirement_result.excluded_resources,
                    recommendation_id,
                    request_id,
                    requirement_ids.get("human"),
                    request.metadata.tenant_id,
                )

            # Insert gaps and alternatives
            for gap in recommendation.resource_gaps:
                gap_id = await self._insert_gap(
                    session,
                    gap,
                    recommendation_id,
                    request_id,
                    request.metadata.tenant_id,
                    requirement_ids.get("human") if gap.resource_type.value == "HUMAN" else None,
                )

                # Alternatives are stored separately in the recommendation, not in the gap
                for alt_seq, alternative in enumerate(recommendation.alternatives, start=1):
                    await self._insert_alternative(
                        session,
                        alternative,
                        gap_id,
                        recommendation_id,
                        request.metadata.tenant_id,
                        alt_seq,
                    )

            # Insert budget validation results
            if recommendation.budget_requirement_result:
                if recommendation.budget_requirement_result.budget_validation:
                    await self._insert_budget_validation(
                        session,
                        recommendation.budget_requirement_result.budget_validation,
                        recommendation_id,
                        request_id,
                        requirement_ids.get("budget"),
                        request.metadata.tenant_id,
                    )

            # Insert evidence links
            await self._insert_evidence_links(
                session,
                recommendation,
                recommendation_id,
                request.metadata.tenant_id,
            )

            return recommendation_id

    async def get_recommendation(
        self,
        tenant_id: UUID,
        recommendation_id: UUID,
    ) -> Optional[Dict[str, Any]]:
        """Get a recommendation by ID.

        Args:
            tenant_id: The tenant ID
            recommendation_id: The recommendation ID

        Returns:
            The recommendation header or None if not found
        """
        async with self._session_factory() as session:
            result = await session.execute(
                text(SQL_SELECT_RECOMMENDATION_HEADER),
                {
                    "tenant_id": tenant_id,
                    "recommendation_id": recommendation_id,
                },
            )
            row = result.fetchone()
            return dict(row._mapping) if row else None

    async def get_latest_recommendation_by_correlation_id(
        self,
        tenant_id: UUID,
        correlation_id: UUID,
    ) -> Optional[Dict[str, Any]]:
        """Get the latest recommendation by correlation ID.

        Args:
            tenant_id: The tenant ID
            correlation_id: The correlation ID

        Returns:
            The recommendation header or None if not found
        """
        async with self._session_factory() as session:
            result = await session.execute(
                text(SQL_SELECT_LATEST_RECOMMENDATION_HEADER),
                {
                    "tenant_id": tenant_id,
                    "correlation_id": correlation_id,
                },
            )
            row = result.fetchone()
            return dict(row._mapping) if row else None

    async def mark_previous_recommendation_superseded(
        self,
        tenant_id: UUID,
        correlation_id: UUID,
        new_recommendation_id: UUID,
    ) -> None:
        """Mark previous recommendations as superseded.

        Args:
            tenant_id: The tenant ID
            correlation_id: The correlation ID
            new_recommendation_id: The new recommendation ID
        """
        async with self._transaction() as session:
            await session.execute(
                text(SQL_MARK_SUPERSEDED),
                {
                    "tenant_id": tenant_id,
                    "correlation_id": correlation_id,
                    "new_recommendation_id": new_recommendation_id,
                },
            )

    # Private helper methods

    async def _check_idempotency(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        correlation_id: UUID,
    ) -> Optional[Dict[str, Any]]:
        """Check if request already exists by idempotency key."""
        idempotency_key = f"{correlation_id}_{tenant_id}"
        result = await session.execute(
            text(SQL_SELECT_REQUEST_BY_IDEMPOTENCY),
            {
                "tenant_id": tenant_id,
                "idempotency_key": idempotency_key,
            },
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def _get_existing_recommendation(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        request_id: UUID,
    ) -> Optional[UUID]:
        """Get existing recommendation ID for a request."""
        result = await session.execute(
            text(SQL_SELECT_RECOMMENDATION_ID_BY_REQUEST),
            {
                "tenant_id": tenant_id,
                "request_id": request_id,
            },
        )
        row = result.fetchone()
        return row[0] if row else None

    async def _insert_request(
        self,
        session: AsyncSession,
        request: AllocationRequest,
        evaluation_timestamp: datetime,
    ) -> UUID:
        """Insert allocation request."""
        request_data = map_request_to_allocation_request(request, evaluation_timestamp)
        result = await session.execute(
            text(SQL_INSERT_ALLOCATION_REQUEST),
            request_data,
        )
        row = result.fetchone()
        return row[0] if row else request_data["id"]

    async def _insert_requirement(
        self,
        session: AsyncSession,
        requirement: HumanResourceRequirement | BudgetResourceRequirement,
        request_id: UUID,
        tenant_id: UUID,
        sequence_order: int,
    ) -> UUID:
        """Insert allocation requirement."""
        requirement_data = map_requirement_to_allocation_requirement(
            requirement,
            request_id,
            tenant_id,
            sequence_order,
        )
        await session.execute(
            text(SQL_INSERT_ALLOCATION_REQUIREMENT),
            requirement_data,
        )
        return requirement_data["id"]

    async def _get_next_version(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        correlation_id: UUID,
    ) -> int:
        """Get next recommendation version."""
        result = await session.execute(
            text(SQL_SELECT_NEXT_RECOMMENDATION_VERSION),
            {
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
            },
        )
        row = result.fetchone()
        return row[0] if row else 1

    async def _insert_recommendation(
        self,
        session: AsyncSession,
        recommendation: AllocationRecommendation,
        request_id: UUID,
        tenant_id: UUID,
        version: int,
    ) -> UUID:
        """Insert allocation recommendation."""
        recommendation_data = map_recommendation_to_allocation_recommendation(
            recommendation,
            request_id,
            tenant_id,
            version,
        )
        await session.execute(
            text(SQL_INSERT_ALLOCATION_RECOMMENDATION),
            recommendation_data,
        )
        return recommendation_data["id"]

    async def _mark_superseded(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        correlation_id: UUID,
        new_recommendation_id: UUID,
    ) -> None:
        """Mark previous recommendations as superseded."""
        await session.execute(
            text(SQL_MARK_SUPERSEDED),
            {
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "new_recommendation_id": new_recommendation_id,
            },
        )

    async def _insert_candidates(
        self,
        session: AsyncSession,
        candidates: List[RankedCandidate],
        recommendation_id: UUID,
        request_id: UUID,
        requirement_id: Optional[UUID],
        tenant_id: UUID,
    ) -> None:
        """Insert allocation candidates."""
        for rank, candidate in enumerate(candidates, start=1):
            candidate_data = map_candidate_to_allocation_candidate(
                candidate,
                recommendation_id,
                request_id,
                requirement_id or uuid4(),  # Fallback if no requirement
                tenant_id,
                rank,
            )
            await session.execute(
                text(SQL_INSERT_ALLOCATION_CANDIDATE),
                candidate_data,
            )

    async def _insert_exclusions(
        self,
        session: AsyncSession,
        exclusions: List[ExcludedResource],
        recommendation_id: UUID,
        request_id: UUID,
        requirement_id: Optional[UUID],
        tenant_id: UUID,
    ) -> None:
        """Insert allocation exclusions and reasons."""
        for excluded in exclusions:
            exclusion_data = map_exclusion_to_allocation_exclusion(
                excluded,
                recommendation_id,
                request_id,
                requirement_id or uuid4(),  # Fallback if no requirement
                tenant_id,
            )
            result = await session.execute(
                text(SQL_INSERT_ALLOCATION_EXCLUSION),
                exclusion_data,
            )
            row = result.fetchone()
            if row:
                exclusion_id = row[0]

                # Insert reasons
                for seq, reason in enumerate(excluded.exclusion_reasons, start=1):
                    reason_data = map_exclusion_reason_to_allocation_exclusion_reason(
                        reason,
                        exclusion_id,
                        tenant_id,
                        seq,
                    )
                    await session.execute(
                        text(SQL_INSERT_ALLOCATION_EXCLUSION_REASON),
                        reason_data,
                    )

    async def _insert_gap(
        self,
        session: AsyncSession,
        gap: ResourceGap,
        recommendation_id: UUID,
        request_id: UUID,
        tenant_id: UUID,
        requirement_id: Optional[UUID],
    ) -> UUID:
        """Insert resource gap."""
        gap_data = map_gap_to_resource_gap(
            gap,
            recommendation_id,
            request_id,
            tenant_id,
            requirement_id,
        )
        await session.execute(
            text(SQL_INSERT_RESOURCE_GAP),
            gap_data,
        )
        return gap_data["id"]

    async def _insert_alternative(
        self,
        session: AsyncSession,
        alternative: ResourceAlternative,
        gap_id: UUID,
        recommendation_id: UUID,
        tenant_id: UUID,
        sequence_order: int,
    ) -> None:
        """Insert resource alternative."""
        alternative_data = map_alternative_to_resource_alternative(
            alternative,
            gap_id,
            recommendation_id,
            tenant_id,
            sequence_order,
        )
        await session.execute(
            text(SQL_INSERT_RESOURCE_ALTERNATIVE),
            alternative_data,
        )

    async def _insert_budget_validation(
        self,
        session: AsyncSession,
        validation: BudgetValidationChecks,
        recommendation_id: UUID,
        request_id: UUID,
        requirement_id: Optional[UUID],
        tenant_id: UUID,
    ) -> None:
        """Insert budget validation result."""
        validation_data = map_budget_validation_to_budget_validation_result(
            validation,
            recommendation_id,
            request_id,
            requirement_id or uuid4(),
            tenant_id,
            uuid4(),  # resource_id placeholder
        )
        await session.execute(
            text(SQL_INSERT_BUDGET_VALIDATION),
            validation_data,
        )

    async def _insert_evidence_links(
        self,
        session: AsyncSession,
        recommendation: AllocationRecommendation,
        recommendation_id: UUID,
        tenant_id: UUID,
    ) -> None:
        """Insert evidence links."""
        # Extract evidence from results and insert links
        seq = 1
        if recommendation.human_requirement_result:
            for candidate in recommendation.human_requirement_result.eligible_candidates:
                if candidate.evidence_refs:
                    for key, ref_id in candidate.evidence_refs.items():
                        link_data = map_evidence_link_to_recommendation_evidence_link(
                            key,
                            ref_id,
                            candidate.resource_id,
                            "candidate_evidence",
                            recommendation_id,
                            tenant_id,
                            seq,
                        )
                        await session.execute(
                            text(SQL_INSERT_EVIDENCE_LINK),
                            link_data,
                        )
                        seq += 1
