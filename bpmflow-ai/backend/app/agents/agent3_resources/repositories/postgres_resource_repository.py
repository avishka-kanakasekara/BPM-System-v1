"""PostgreSQL read-path repository for Agent 3 resource evidence."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Dict, List, Mapping, Optional, Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import ResourceLookupError
from ..interfaces import ResourceRepository
from ..schemas import BudgetResourceEvidence, HumanResourceEvidence
from .exceptions import MappingError, MissingEvidenceError
from .mappers import map_budget_resource_evidence, map_human_resource_evidence
from .table_mapping import (
    SQL_SELECT_AVAILABILITY,
    SQL_SELECT_BUDGET_PROFILES,
    SQL_SELECT_BUDGET_RESOURCES,
    SQL_SELECT_DECLARED_CONFLICTS,
    SQL_SELECT_EVIDENCE_REFERENCES,
    SQL_SELECT_HUMAN_PROFILES,
    SQL_SELECT_HUMAN_RESOURCES,
    SQL_SELECT_RESOURCE_AUTHORITIES,
    SQL_SELECT_RESOURCE_ROLES,
    SQL_SELECT_RESOURCE_SKILLS,
    SQL_SELECT_WORKLOAD_SNAPSHOTS,
)


SessionFactory = Callable[[], AsyncSession]


class PostgresResourceRepository(ResourceRepository):
    """Load Agent 3 evidence models from normalized PostgreSQL read-path tables."""

    def __init__(
        self,
        session_factory: Optional[SessionFactory] = None,
        session: Optional[AsyncSession] = None,
    ):
        if session_factory is None and session is None:
            raise ValueError("PostgresResourceRepository requires session_factory or session")
        if session_factory is not None and session is not None:
            raise ValueError("Provide only one of session_factory or session")
        self._session_factory = session_factory
        self._session = session

    @asynccontextmanager
    async def _session_scope(self) -> AsyncIterator[AsyncSession]:
        if self._session is not None:
            yield self._session
            return
        assert self._session_factory is not None
        session = self._session_factory()
        try:
            yield session
        finally:
            await session.close()

    async def get_human_resources_by_tenant(
        self,
        tenant_id: UUID,
        evaluation_timestamp: datetime,
    ) -> List[HumanResourceEvidence]:
        try:
            async with self._session_scope() as session:
                resource_rows = await self._fetch_all(
                    session,
                    SQL_SELECT_HUMAN_RESOURCES,
                    {"tenant_id": tenant_id},
                )
                if not resource_rows:
                    return []

                resource_ids = [row["id"] for row in resource_rows]
                params = {
                    "tenant_id": tenant_id,
                    "resource_ids": resource_ids,
                    "evaluation_timestamp": evaluation_timestamp,
                }

                roles_by_resource = self._group_codes(
                    await self._fetch_all(session, SQL_SELECT_RESOURCE_ROLES, params)
                )
                skills_by_resource = self._group_codes(
                    await self._fetch_all(session, SQL_SELECT_RESOURCE_SKILLS, params)
                )
                authorities_by_resource = self._group_codes(
                    await self._fetch_all(
                        session, SQL_SELECT_RESOURCE_AUTHORITIES, params
                    ),
                    single=True,
                )
                profiles = self._index_by_resource_id(
                    await self._fetch_all(session, SQL_SELECT_HUMAN_PROFILES, params)
                )
                availability = self._first_by_resource_id(
                    await self._fetch_all(session, SQL_SELECT_AVAILABILITY, params)
                )
                workloads = self._latest_snapshot_by_resource(
                    await self._fetch_all(
                        session, SQL_SELECT_WORKLOAD_SNAPSHOTS, params
                    )
                )
                evidence = self._group_rows_by_resource(
                    await self._fetch_all(
                        session, SQL_SELECT_EVIDENCE_REFERENCES, params
                    )
                )
                conflicts = await self._fetch_all(
                    session, SQL_SELECT_DECLARED_CONFLICTS, params
                )
                sod_by_resource, coi_by_resource = self._split_conflicts(conflicts)

                results: List[HumanResourceEvidence] = []
                for resource_row in resource_rows:
                    resource_id = resource_row["id"]
                    profile_row = profiles.get(resource_id)
                    if profile_row is None:
                        continue
                    try:
                        results.append(
                            map_human_resource_evidence(
                                resource_row,
                                expected_tenant_id=tenant_id,
                                roles=roles_by_resource.get(resource_id, []),
                                skills=skills_by_resource.get(resource_id, []),
                                authority=authorities_by_resource.get(resource_id),
                                availability_row=availability.get(resource_id),
                                workload_row=workloads.get(resource_id),
                                profile_row=profile_row,
                                sod_conflicts=sod_by_resource.get(resource_id, []),
                                coi_flags=coi_by_resource.get(resource_id, []),
                                evidence_rows=evidence.get(resource_id, []),
                            )
                        )
                    except (MissingEvidenceError, MappingError):
                        continue
                return results
        except SQLAlchemyError as exc:
            raise ResourceLookupError(str(exc)) from exc

    async def get_budget_resources_by_tenant(
        self,
        tenant_id: UUID,
        evaluation_timestamp: datetime,
    ) -> List[BudgetResourceEvidence]:
        try:
            async with self._session_scope() as session:
                resource_rows = await self._fetch_all(
                    session,
                    SQL_SELECT_BUDGET_RESOURCES,
                    {"tenant_id": tenant_id},
                )
                if not resource_rows:
                    return []

                resource_ids = [row["id"] for row in resource_rows]
                params = {
                    "tenant_id": tenant_id,
                    "resource_ids": resource_ids,
                    "evaluation_timestamp": evaluation_timestamp,
                }
                profiles = self._index_by_resource_id(
                    await self._fetch_all(session, SQL_SELECT_BUDGET_PROFILES, params)
                )
                evidence = self._group_rows_by_resource(
                    await self._fetch_all(
                        session, SQL_SELECT_EVIDENCE_REFERENCES, params
                    )
                )

                results: List[BudgetResourceEvidence] = []
                for resource_row in resource_rows:
                    resource_id = resource_row["id"]
                    profile_row = profiles.get(resource_id)
                    if profile_row is None:
                        continue
                    try:
                        results.append(
                            map_budget_resource_evidence(
                                resource_row,
                                profile_row,
                                evidence.get(resource_id, []),
                                expected_tenant_id=tenant_id,
                            )
                        )
                    except (MissingEvidenceError, MappingError):
                        continue
                return results
        except SQLAlchemyError as exc:
            raise ResourceLookupError(str(exc)) from exc

    @staticmethod
    async def _fetch_all(
        session: AsyncSession,
        sql: str,
        params: Mapping[str, Any],
    ) -> List[Dict[str, Any]]:
        result = await session.execute(text(sql), dict(params))
        return [dict(row._mapping) for row in result.fetchall()]

    @staticmethod
    def _group_codes(
        rows: Sequence[Mapping[str, Any]],
        *,
        single: bool = False,
    ) -> Dict[Any, Any]:
        grouped: Dict[Any, Any] = {}
        for row in rows:
            resource_id = row["resource_id"]
            code = row["code"]
            if single:
                grouped[resource_id] = code
            else:
                grouped.setdefault(resource_id, []).append(code)
        return grouped

    @staticmethod
    def _index_by_resource_id(rows: Sequence[Mapping[str, Any]]) -> Dict[Any, Dict[str, Any]]:
        return {row["resource_id"]: dict(row) for row in rows}

    @staticmethod
    def _first_by_resource_id(rows: Sequence[Mapping[str, Any]]) -> Dict[Any, Dict[str, Any]]:
        grouped: Dict[Any, Dict[str, Any]] = {}
        for row in rows:
            resource_id = row["resource_id"]
            if resource_id not in grouped:
                grouped[resource_id] = dict(row)
        return grouped

    @staticmethod
    def _latest_snapshot_by_resource(
        rows: Sequence[Mapping[str, Any]],
    ) -> Dict[Any, Dict[str, Any]]:
        grouped: Dict[Any, Dict[str, Any]] = {}
        for row in rows:
            resource_id = row["resource_id"]
            if resource_id not in grouped:
                grouped[resource_id] = dict(row)
        return grouped

    @staticmethod
    def _group_rows_by_resource(
        rows: Sequence[Mapping[str, Any]],
    ) -> Dict[Any, List[Dict[str, Any]]]:
        grouped: Dict[Any, List[Dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row["resource_id"], []).append(dict(row))
        return grouped

    @staticmethod
    def _split_conflicts(
        rows: Sequence[Mapping[str, Any]],
    ) -> tuple[Dict[Any, List[UUID]], Dict[Any, List[str]]]:
        sod: Dict[Any, List[UUID]] = {}
        coi: Dict[Any, List[str]] = {}
        for row in rows:
            resource_id = row["resource_id"]
            conflicting_resource_id = row.get("conflicting_resource_id")
            conflict_flag_code = row.get("conflict_flag_code")
            if conflicting_resource_id is not None:
                sod.setdefault(resource_id, []).append(UUID(str(conflicting_resource_id)))
            if conflict_flag_code:
                coi.setdefault(resource_id, []).append(str(conflict_flag_code))
        return sod, coi
