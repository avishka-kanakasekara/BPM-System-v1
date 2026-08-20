"""API tests for AUDIT endpoints. No live Supabase database is required."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.agents.agent4_orchestrator.audit_repository import (
    DEFAULT_AUDIT_LIMIT,
    MAX_AUDIT_LIMIT,
    AuditLogRecord,
    InMemoryAuditRepository,
)
from app.agents.agent4_orchestrator.exceptions import DatabasePersistenceError
from app.agents.agent4_orchestrator.repository import AUDIT_ENTITY_PROCESS
from app.api.v1.deps import get_audit_repository
from app.main import app

UTC = timezone.utc
BASE_TIME = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def audit_setup():
    repository = InMemoryAuditRepository()

    async def override_repository() -> InMemoryAuditRepository:
        return repository

    app.dependency_overrides[get_audit_repository] = override_repository

    yield {
        "client": TestClient(app),
        "repository": repository,
    }

    app.dependency_overrides.clear()


def _add_record(
    repository: InMemoryAuditRepository,
    *,
    entity_type: str = AUDIT_ENTITY_PROCESS,
    entity_id=None,
    action: str = "updated",
    minutes_offset: int = 0,
) -> AuditLogRecord:
    record = AuditLogRecord(
        id=uuid4(),
        entity_type=entity_type,
        entity_id=entity_id or uuid4(),
        action=action,
        performed_by=None,
        old_values={"status": "open"},
        new_values={"status": "resolved"},
        timestamp=BASE_TIME + timedelta(minutes=minutes_offset),
    )
    repository.add_record(record)
    return record


def test_list_audit_logs(audit_setup) -> None:
    setup = audit_setup
    _add_record(setup["repository"], action="created", minutes_offset=0)
    _add_record(setup["repository"], action="updated", minutes_offset=1)

    response = setup["client"].get("/api/v1/audit")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["action"] == "updated"
    assert body[1]["action"] == "created"


def test_audit_records_returned_newest_first(audit_setup) -> None:
    setup = audit_setup
    older = _add_record(setup["repository"], action="older", minutes_offset=0)
    newer = _add_record(setup["repository"], action="newer", minutes_offset=10)

    response = setup["client"].get("/api/v1/audit")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["id"] == str(newer.id)
    assert body[1]["id"] == str(older.id)


def test_filter_by_entity_type(audit_setup) -> None:
    setup = audit_setup
    process_record = _add_record(
        setup["repository"],
        entity_type=AUDIT_ENTITY_PROCESS,
        minutes_offset=1,
    )
    _add_record(setup["repository"], entity_type="task", minutes_offset=2)

    response = setup["client"].get(
        "/api/v1/audit",
        params={"entity_type": AUDIT_ENTITY_PROCESS},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(process_record.id)
    assert body[0]["entity_type"] == AUDIT_ENTITY_PROCESS


def test_filter_by_entity_id(audit_setup) -> None:
    setup = audit_setup
    entity_id = uuid4()
    match = _add_record(setup["repository"], entity_id=entity_id, minutes_offset=1)
    _add_record(setup["repository"], minutes_offset=2)

    response = setup["client"].get(
        "/api/v1/audit",
        params={"entity_id": str(entity_id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(match.id)
    assert body[0]["entity_id"] == str(entity_id)


def test_filter_by_entity_type_and_entity_id(audit_setup) -> None:
    setup = audit_setup
    entity_id = uuid4()
    match = _add_record(
        setup["repository"],
        entity_type=AUDIT_ENTITY_PROCESS,
        entity_id=entity_id,
        minutes_offset=3,
    )
    _add_record(
        setup["repository"],
        entity_type=AUDIT_ENTITY_PROCESS,
        minutes_offset=2,
    )
    _add_record(
        setup["repository"],
        entity_type="task",
        entity_id=entity_id,
        minutes_offset=1,
    )

    response = setup["client"].get(
        "/api/v1/audit",
        params={
            "entity_type": AUDIT_ENTITY_PROCESS,
            "entity_id": str(entity_id),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(match.id)


def test_invalid_entity_id_returns_422(audit_setup) -> None:
    response = audit_setup["client"].get(
        "/api/v1/audit",
        params={"entity_id": "not-a-uuid"},
    )
    assert response.status_code == 422


def test_default_limit_is_applied(audit_setup) -> None:
    setup = audit_setup
    for minute in range(60):
        _add_record(setup["repository"], minutes_offset=minute)

    response = setup["client"].get("/api/v1/audit")

    assert response.status_code == 200
    assert len(response.json()) == DEFAULT_AUDIT_LIMIT


def test_maximum_limit_is_enforced(audit_setup) -> None:
    response = audit_setup["client"].get(
        "/api/v1/audit",
        params={"limit": MAX_AUDIT_LIMIT + 1},
    )
    assert response.status_code == 422


def test_offset_works(audit_setup) -> None:
    setup = audit_setup
    records = [
        _add_record(setup["repository"], action=f"event-{minute}", minutes_offset=minute)
        for minute in range(5)
    ]
    records.sort(key=lambda item: item.timestamp, reverse=True)

    response = setup["client"].get(
        "/api/v1/audit",
        params={"limit": 2, "offset": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["id"] == str(records[2].id)
    assert body[1]["id"] == str(records[3].id)


def test_database_failure_returns_503(audit_setup) -> None:
    failing_repo = AsyncMock()
    failing_repo.list_audit_logs.side_effect = DatabasePersistenceError("down")

    async def override_repository():
        return failing_repo

    app.dependency_overrides[get_audit_repository] = override_repository
    client = TestClient(app)

    response = client.get("/api/v1/audit")

    assert response.status_code == 503
    assert response.json()["detail"] == "Database unavailable"
    app.dependency_overrides.clear()


def test_audit_response_includes_json_fields(audit_setup) -> None:
    setup = audit_setup
    record = _add_record(setup["repository"], minutes_offset=0)

    response = setup["client"].get("/api/v1/audit")

    assert response.status_code == 200
    body = response.json()[0]
    assert body["id"] == str(record.id)
    assert body["old_values"] == {"status": "open"}
    assert body["new_values"] == {"status": "resolved"}
    assert body["timestamp"] is not None
