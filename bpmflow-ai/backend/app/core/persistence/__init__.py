"""Unified persistence layer entry points."""

from app.core.persistence.policy import (
    OperationKind,
    PersistenceMode,
    may_use_rest_fallback,
    requires_postgres,
)
from app.core.persistence.repository import (
    PersistenceError,
    assert_postgres_available,
    get_effective_mode,
    probe_and_update_status,
    resolve_backend,
)
from app.core.persistence.status import PersistenceStatus, persistence_status

__all__ = [
    "OperationKind",
    "PersistenceError",
    "PersistenceMode",
    "PersistenceStatus",
    "assert_postgres_available",
    "get_effective_mode",
    "may_use_rest_fallback",
    "persistence_status",
    "probe_and_update_status",
    "requires_postgres",
    "resolve_backend",
]
