# Persistence strategy

## Summary

| Mode | Primary | Fallback | Reported as |
|------|---------|----------|-------------|
| `auto` (default) | Postgres | Supabase REST | `degraded` when on REST |
| `postgres` | Postgres only | none | hard-fail if down |
| `rest` | Supabase REST only | none | always `rest` |

Configure via `PERSISTENCE_MODE` in `backend/.env`.

## Operations

### May use REST fallback (degraded)

- Single-row reads (processes, receipts, users, approvals)
- Single-row writes and upserts exposed via PostgREST
- Health probes

### Must use Postgres (hard-fail)

- Multi-statement transactions
- SQL migrations (`schema_migrations`)
- Agent 3 ranking SQL joins (tenant-scoped complex queries)

## Implementation

- **Policy:** `app/core/persistence/policy.py`
- **Status:** `app/core/persistence/status.py` — updated at startup and on `/health` probes
- **Routing:** `app/core/persistence/repository.py` — call `resolve_backend(OperationKind.READ)` before IO

Repositories should call `use_supabase_rest_fallback()` (which reads `PersistenceStatus`) instead of probing engines ad hoc.

## Health

- `/health/deps` and `/health/ready` include `persistence_mode` and `persistence.degraded`
- Degraded mode is never silent: logs emit `persistence_degraded_using_rest`
