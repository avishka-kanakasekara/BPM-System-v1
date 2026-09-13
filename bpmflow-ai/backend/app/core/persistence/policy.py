"""Persistence fallback policy — single source of truth.

Postgres is primary. Supabase REST is an explicit degraded fallback for a
narrow set of read/write operations when the pooler is unreachable.

Degraded mode is always reported via ``PersistenceStatus`` and health probes;
it must never be silent.
"""

from __future__ import annotations

from enum import Enum


class PersistenceMode(str, Enum):
    """Effective runtime persistence backend."""

    POSTGRES = "postgres"
    REST = "rest"
    UNAVAILABLE = "unavailable"


class OperationKind(str, Enum):
    """Coarse operation classes used for fallback decisions."""

    READ = "read"
    WRITE = "write"
    TRANSACTION = "transaction"
    MIGRATION = "migration"
    HEALTH = "health"


# Operations that MAY use Supabase REST when Postgres is down (degraded).
REST_FALLBACK_ALLOWED: frozenset[OperationKind] = frozenset(
    {
        OperationKind.READ,
        OperationKind.WRITE,
        OperationKind.HEALTH,
    }
)

# Operations that MUST use Postgres — hard-fail when unavailable.
POSTGRES_REQUIRED: frozenset[OperationKind] = frozenset(
    {
        OperationKind.TRANSACTION,
        OperationKind.MIGRATION,
    }
)


def may_use_rest_fallback(kind: OperationKind) -> bool:
    return kind in REST_FALLBACK_ALLOWED


def requires_postgres(kind: OperationKind) -> bool:
    return kind in POSTGRES_REQUIRED
