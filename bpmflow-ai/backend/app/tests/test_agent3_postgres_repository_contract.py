"""Contract tests for Agent 3 PostgreSQL repository (fake session — no live DB)."""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Mapping, Optional, Sequence
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.agents.agent3_resources.constants import ResourceLookupError
from app.agents.agent3_resources.fixtures import (
    FIXTURE_REFERENCE_TIMESTAMP,
    get_requester_id,
    get_tenant_a_id,
    get_tenant_b_id,
)
from app.agents.agent3_resources.interfaces import InMemoryResourceRepository
from app.agents.agent3_resources.repositories.exceptions import CrossTenantGraphError
from app.agents.agent3_resources.repositories.mappers import map_human_resource_evidence
from app.agents.agent3_resources.repositories.postgres_resource_repository import (
    PostgresResourceRepository,
)
from app.agents.agent3_resources.repositories.table_mapping import (
    SQL_SELECT_BUDGET_PROFILES,
    SQL_SELECT_BUDGET_RESOURCES,
    SQL_SELECT_HUMAN_PROFILES,
    SQL_SELECT_HUMAN_RESOURCES,
    SQL_SELECT_WORKLOAD_SNAPSHOTS,
)

UTC = timezone.utc
TENANT_A = get_tenant_a_id()
TENANT_B = get_tenant_b_id()
REQUESTER = get_requester_id()
EVAL_TS = FIXTURE_REFERENCE_TIMESTAMP


class FakeRow:
    def __init__(self, mapping: Mapping[str, Any]):
        self._mapping = dict(mapping)


class FakeResult:
    def __init__(self, rows: Sequence[Mapping[str, Any]]):
        self._rows = [FakeRow(row) for row in rows]

    def fetchall(self) -> List[FakeRow]:
        return self._rows


class FakeSession:
    """Records SQL/params and returns canned rows keyed by SQL constant."""

    def __init__(self, responses: Optional[Dict[str, List[Mapping[str, Any]]]] = None):
        self.executed: List[tuple[str, Dict[str, Any]]] = []
        self._responses = responses or {}
        self.closed = False

    async def execute(self, statement, params: Optional[Dict[str, Any]] = None):
        sql = str(statement)
        bound = dict(params or {})
        self.executed.append((sql, bound))
        for key, rows in self._responses.items():
            if key in sql:
                return FakeResult(rows)
        return FakeResult([])

    async def close(self) -> None:
        self.closed = True


def _human_resource_row(
    resource_id: UUID,
    *,
    tenant_id: UUID = TENANT_A,
    name: str = "Alice",
) -> Dict[str, Any]:
    return {
        "id": resource_id,
        "tenant_id": tenant_id,
        "name": name,
        "is_active": True,
    }


def _human_profile_row(
    resource_id: UUID,
    *,
    tenant_id: UUID = TENANT_A,
) -> Dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "resource_id": resource_id,
        "max_workload_pct": Decimal("80"),
        "evidence_checked_at": EVAL_TS,
        "evidence_valid_until": EVAL_TS.replace(year=EVAL_TS.year + 1),
    }


def _availability_row(
    resource_id: UUID,
    *,
    tenant_id: UUID = TENANT_A,
) -> Dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "resource_id": resource_id,
        "available_from": EVAL_TS.replace(year=EVAL_TS.year - 1),
        "available_until": None,
    }


def _workload_row(
    resource_id: UUID,
    *,
    tenant_id: UUID = TENANT_A,
    snapshot_at: datetime = EVAL_TS,
    current: Decimal = Decimal("40"),
    maximum: Decimal = Decimal("80"),
) -> Dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "resource_id": resource_id,
        "snapshot_at": snapshot_at,
        "current_workload_pct": current,
        "max_workload_pct": maximum,
    }


def _budget_resource_row(
    resource_id: UUID,
    *,
    tenant_id: UUID = TENANT_A,
    name: str = "Ops Budget",
) -> Dict[str, Any]:
    return {
        "id": resource_id,
        "tenant_id": tenant_id,
        "name": name,
        "is_active": True,
    }


def _budget_profile_row(
    resource_id: UUID,
    *,
    tenant_id: UUID = TENANT_A,
) -> Dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "resource_id": resource_id,
        "cost_centre": "CC-100",
        "currency": "USD",
        "available_balance": Decimal("50000.00"),
        "authorization_limit": Decimal("10000.00"),
        "valid_from": EVAL_TS.replace(year=EVAL_TS.year - 1),
        "valid_until": EVAL_TS.replace(year=EVAL_TS.year + 1),
        "evidence_checked_at": EVAL_TS,
        "evidence_valid_until": EVAL_TS.replace(year=EVAL_TS.year + 1),
    }


@pytest.mark.anyio
class TestPostgresResourceRepositoryContract:
    """Fake-session contract tests — not real PostgreSQL integration tests."""

    async def test_tenant_id_reaches_every_query(self):
        resource_id = uuid4()
        session = FakeSession(
            {
                SQL_SELECT_HUMAN_RESOURCES: [_human_resource_row(resource_id)],
                SQL_SELECT_HUMAN_PROFILES: [_human_profile_row(resource_id)],
                "resource_availability": [_availability_row(resource_id)],
                SQL_SELECT_WORKLOAD_SNAPSHOTS: [_workload_row(resource_id)],
            }
        )
        repo = PostgresResourceRepository(session=session)
        await repo.get_human_resources_by_tenant(TENANT_A, EVAL_TS)

        assert session.executed
        for _, params in session.executed:
            assert "tenant_id" in params
            assert params["tenant_id"] == TENANT_A

    async def test_requester_id_never_used_as_tenant_filter(self):
        resource_id = uuid4()
        session = FakeSession(
            {
                SQL_SELECT_HUMAN_RESOURCES: [_human_resource_row(resource_id)],
                SQL_SELECT_HUMAN_PROFILES: [_human_profile_row(resource_id)],
                "resource_availability": [_availability_row(resource_id)],
                SQL_SELECT_WORKLOAD_SNAPSHOTS: [_workload_row(resource_id)],
            }
        )
        repo = PostgresResourceRepository(session=session)
        await repo.get_human_resources_by_tenant(TENANT_A, EVAL_TS)

        for sql, params in session.executed:
            assert str(REQUESTER) not in sql
            for value in params.values():
                assert value != REQUESTER

    async def test_human_queries_request_human_only(self):
        session = FakeSession({SQL_SELECT_HUMAN_RESOURCES: []})
        repo = PostgresResourceRepository(session=session)
        await repo.get_human_resources_by_tenant(TENANT_A, EVAL_TS)

        human_sql = next(sql for sql, _ in session.executed if "FROM resources" in sql)
        assert "type = 'HUMAN'" in human_sql.replace("\n", " ")

    async def test_budget_queries_request_budget_only(self):
        session = FakeSession({SQL_SELECT_BUDGET_RESOURCES: []})
        repo = PostgresResourceRepository(session=session)
        await repo.get_budget_resources_by_tenant(TENANT_A, EVAL_TS)

        budget_sql = next(sql for sql, _ in session.executed if "FROM resources" in sql)
        assert "type = 'BUDGET'" in budget_sql.replace("\n", " ")

    async def test_stable_ordering_is_preserved(self):
        id_a = UUID("11111111-1111-1111-1111-111111111111")
        id_b = UUID("22222222-2222-2222-2222-222222222222")
        session = FakeSession(
            {
                SQL_SELECT_HUMAN_RESOURCES: [
                    _human_resource_row(id_b, name="Bravo"),
                    _human_resource_row(id_a, name="Alpha"),
                ],
                SQL_SELECT_HUMAN_PROFILES: [
                    _human_profile_row(id_b),
                    _human_profile_row(id_a),
                ],
                "resource_availability": [
                    _availability_row(id_b),
                    _availability_row(id_a),
                ],
                SQL_SELECT_WORKLOAD_SNAPSHOTS: [
                    _workload_row(id_b),
                    _workload_row(id_a),
                ],
            }
        )
        repo = PostgresResourceRepository(session=session)
        results = await repo.get_human_resources_by_tenant(TENANT_A, EVAL_TS)

        assert [r.resource_id for r in results] == [id_b, id_a]
        human_sql = next(sql for sql, _ in session.executed if "ORDER BY id ASC" in sql)
        assert human_sql

    async def test_cross_tenant_row_graphs_are_rejected(self):
        resource_id = uuid4()
        with pytest.raises(CrossTenantGraphError):
            map_human_resource_evidence(
                _human_resource_row(resource_id, tenant_id=TENANT_A),
                expected_tenant_id=TENANT_A,
                roles=["developer"],
                skills=["python"],
                authority="senior",
                availability_row=_availability_row(resource_id, tenant_id=TENANT_B),
                workload_row=_workload_row(resource_id),
                profile_row=_human_profile_row(resource_id),
                sod_conflicts=[],
                coi_flags=[],
                evidence_rows=[],
            )

    async def test_human_evidence_maps_correctly(self):
        resource_id = uuid4()
        session = FakeSession(
            {
                SQL_SELECT_HUMAN_RESOURCES: [_human_resource_row(resource_id, name="Carol")],
                "resource_roles": [
                    {"resource_id": resource_id, "tenant_id": TENANT_A, "code": "developer"}
                ],
                "resource_skills": [
                    {"resource_id": resource_id, "tenant_id": TENANT_A, "code": "python"}
                ],
                "resource_authorities": [
                    {"resource_id": resource_id, "tenant_id": TENANT_A, "code": "senior"}
                ],
                SQL_SELECT_HUMAN_PROFILES: [_human_profile_row(resource_id)],
                "resource_availability": [_availability_row(resource_id)],
                SQL_SELECT_WORKLOAD_SNAPSHOTS: [
                    _workload_row(resource_id, current=Decimal("35"))
                ],
                "resource_declared_conflicts": [],
                "evidence_references": [
                    {
                        "tenant_id": TENANT_A,
                        "resource_id": resource_id,
                        "evidence_key": "hr_profile",
                        "payload": {"source": "test"},
                        "checked_at": EVAL_TS,
                        "valid_until": EVAL_TS.replace(year=EVAL_TS.year + 1),
                    }
                ],
            }
        )
        repo = PostgresResourceRepository(session=session)
        results = await repo.get_human_resources_by_tenant(TENANT_A, EVAL_TS)

        assert len(results) == 1
        evidence = results[0]
        assert evidence.name == "Carol"
        assert evidence.roles == ["developer"]
        assert evidence.mandatory_skills == ["python"]
        assert evidence.preferred_skills == []
        assert evidence.authority == "senior"
        assert evidence.current_workload_percentage == Decimal("35")
        assert evidence.projected_workload_percentage == Decimal("35")
        assert evidence.evidence_references["hr_profile"] == {"source": "test"}

    async def test_budget_values_remain_decimal(self):
        resource_id = uuid4()
        session = FakeSession(
            {
                SQL_SELECT_BUDGET_RESOURCES: [_budget_resource_row(resource_id)],
                SQL_SELECT_BUDGET_PROFILES: [_budget_profile_row(resource_id)],
                "evidence_references": [],
            }
        )
        repo = PostgresResourceRepository(session=session)
        results = await repo.get_budget_resources_by_tenant(TENANT_A, EVAL_TS)

        assert len(results) == 1
        budget = results[0]
        assert isinstance(budget.available_balance, Decimal)
        assert isinstance(budget.authorization_limit, Decimal)
        assert budget.available_balance == Decimal("50000.00")
        assert budget.authorization_limit == Decimal("10000.00")

    async def test_timezone_aware_datetimes_are_preserved(self):
        resource_id = uuid4()
        session = FakeSession(
            {
                SQL_SELECT_HUMAN_RESOURCES: [_human_resource_row(resource_id)],
                SQL_SELECT_HUMAN_PROFILES: [_human_profile_row(resource_id)],
                "resource_availability": [_availability_row(resource_id)],
                SQL_SELECT_WORKLOAD_SNAPSHOTS: [_workload_row(resource_id)],
            }
        )
        repo = PostgresResourceRepository(session=session)
        results = await repo.get_human_resources_by_tenant(TENANT_A, EVAL_TS)

        evidence = results[0]
        assert evidence.available_from.tzinfo is not None
        assert evidence.evidence_checked_at.tzinfo is not None
        assert evidence.evidence_valid_until.tzinfo is not None

    def test_naive_datetimes_are_rejected(self):
        resource_id = uuid4()
        naive = datetime(2026, 1, 1, 12, 0, 0)
        with pytest.raises(Exception):
            map_human_resource_evidence(
                _human_resource_row(resource_id),
                expected_tenant_id=TENANT_A,
                roles=[],
                skills=[],
                authority=None,
                availability_row={
                    "tenant_id": TENANT_A,
                    "resource_id": resource_id,
                    "available_from": naive,
                    "available_until": None,
                },
                workload_row=_workload_row(resource_id),
                profile_row=_human_profile_row(resource_id),
                sod_conflicts=[],
                coi_flags=[],
                evidence_rows=[],
            )

    async def test_latest_workload_snapshot_query_filters_by_evaluation_time(self):
        resource_id = uuid4()
        session = FakeSession(
            {
                SQL_SELECT_HUMAN_RESOURCES: [_human_resource_row(resource_id)],
                SQL_SELECT_HUMAN_PROFILES: [_human_profile_row(resource_id)],
                "resource_availability": [_availability_row(resource_id)],
                SQL_SELECT_WORKLOAD_SNAPSHOTS: [_workload_row(resource_id)],
            }
        )
        repo = PostgresResourceRepository(session=session)
        await repo.get_human_resources_by_tenant(TENANT_A, EVAL_TS)

        workload_sql = next(
            sql for sql, params in session.executed if "workload_snapshots" in sql
        )
        assert "snapshot_at <= :evaluation_timestamp" in workload_sql.replace("\n", " ")
        assert "ORDER BY resource_id, snapshot_at DESC" in workload_sql.replace("\n", " ")
        _, params = next(
            item for item in session.executed if "workload_snapshots" in item[0]
        )
        assert params["evaluation_timestamp"] == EVAL_TS

    async def test_db_lookup_exceptions_become_resource_lookup_error(self):
        class ErrorSession:
            async def execute(self, *_args, **_kwargs):
                raise SQLAlchemyError("connection failed")

            async def close(self) -> None:
                pass

        repo = PostgresResourceRepository(session=ErrorSession())
        with pytest.raises(ResourceLookupError, match="connection failed"):
            await repo.get_human_resources_by_tenant(TENANT_A, EVAL_TS)

    def test_repository_contains_no_scoring_or_eligibility_behavior(self):
        source = inspect.getsource(PostgresResourceRepository)
        forbidden = (
            "SCORING_WEIGHTS",
            "ExclusionReason",
            "eligible",
            "rank",
            "score",
            "gap",
            "explain",
        )
        lowered = source.lower()
        for token in forbidden:
            assert token.lower() not in lowered

    def test_in_memory_resource_repository_remains_unchanged(self):
        repo = InMemoryResourceRepository()
        assert hasattr(repo, "add_human_resource")
        assert hasattr(repo, "add_budget_resource")
        assert hasattr(repo, "clear")
        human_sig = inspect.signature(repo.get_human_resources_by_tenant)
        budget_sig = inspect.signature(repo.get_budget_resources_by_tenant)
        assert "tenant_id" in human_sig.parameters
        assert "evaluation_timestamp" in human_sig.parameters
        assert "tenant_id" in budget_sig.parameters
        assert "evaluation_timestamp" in budget_sig.parameters
