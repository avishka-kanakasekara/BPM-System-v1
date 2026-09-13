# BPMFlow AI — Architecture (as implemented)

**Last verified:** 2026-09-13 via `e2e_smoke` (8/8) and pytest.

## Overview

Single FastAPI process hosts four agents and shared services. The React frontend talks to `/api/v1/*` with Supabase JWTs. Persistence is **Postgres when reachable**, otherwise **Supabase REST** (explicit degraded mode — no silent `session=None` in API routes).

```
Browser ──JWT──► FastAPI (main.py)
                    ├── Agent 1  document discovery
                    ├── Agent 2  tool execution + scheduler
                    ├── Agent 3  resource ranking (tenant-scoped)
                    ├── Agent 4  state machine + risk + approvals
                    ├── Policy KB  ingestion + retrieval
                    └── Supabase REST / Postgres
```

## Entry & middleware

`backend/app/main.py`:

- Lifespan: prod config assert, DB init, Agent 2 scheduler start/stop, graceful drain
- Middleware (outer→inner): `CorrelationMiddleware` → `RateLimitMiddleware` → `RequestGuardMiddleware` → CORS
- Health: `/health/live` (process up), `/health/ready`, `/health/deps` (per-dependency probes)

## Agents

### Agent 1 — Discovery

- **Routes:** `POST /api/v1/agent1/discover`, `GET /api/v1/agent1/processes/{id}`
- **Pipeline:** ingest → extract → classify → entities/relations (LLM or mock) → PM4Py mining → `process_json` + `risk_facts`
- **Persistence:** updates `processes.process_json`, tasks, exceptions, `agent_messages` (discovery row)

### Agent 2 — Execution

- **Routes:** `/api/v1/agent2/*` (execute, receipts, tools, dashboard, scheduler)
- **Pipeline:** cognitive plan → tool guard → receipt persistence
- **Offline mode:** `GEMINI_OFFLINE=true` uses deterministic tool selection (required for smoke/CI)
- **Scheduler:** polls `scheduled_jobs` via REST; claims with worker id

### Agent 3 — Resources

- **Routes:** `POST /api/v1/agent3/allocations`, recommendation lookups
- **Auth:** ES256 JWT + mandatory `app_metadata.tenant_id`
- **Data:** demo tenant seed (`00000000-0000-0000-0000-000000000001`) with humans, budgets, SoD scenarios

### Agent 4 — Orchestrator

- **Routes:** `/api/v1/processes/*`, `/api/v1/approvals/*`, `/api/v1/exceptions/*`
- **State machine:** DRAFT → DISCOVERING → RESOURCE_PLANNING → RISK_REVIEW → AWAITING_HUMAN_APPROVAL → WORKFLOW_EXECUTION → INVOICE_MATCHING → COMPLETED | EXCEPTION
- **Advancement:** `POST /processes/{id}/advance` chains autonomous steps; idempotency via `process_advancement_runs` (REST) or in-memory fallback when migration 0014 missing
- **Messaging:** `AgentCommunicationService` persists outbound/inbound envelopes to `agent_messages` (REST)
- **Risk:** policy retrieval when `company_policies` exists; else rule-based thresholds from discovery `risk_facts`

## Shared modules (Phase 8+)

| Module | Role |
|--------|------|
| `app/core/audit_writer.py` | Unified `audit_logs` writer |
| `app/core/persistence/` | Mode detection (`postgres` / `rest` / unavailable) |
| `app/messaging/envelope.py` | Inter-agent envelope factory |
| `app/services/email.py` | Email dispatch entry |
| `app/llm/retry.py` | Transient LLM error detection |
| `app/core/logging.py` | JSON logs + `correlation_id` + redaction |

## Frontend

- Vite + React + Tailwind; routes in `frontend/src/App.tsx`
- Process detail page: stage-aware actions, correlation timeline, risk findings
- RBAC: `RequireRole` on `/approvals`, `/policies`, `/tasks`
- Types generated from OpenAPI: `npm run generate:api-types`

## Persistence notes

- **REST fallback:** When pooler DNS fails, repositories use Supabase REST with service role
- **Discovery metadata:** `process_from_rest()` merges `process_json` column + legacy `description` JSON into `metadata_json` for Agent 4 enrichment
- **Missing migrations:** Advancement idempotency degrades to in-memory; apply `0014_process_advancement.sql` for durable runs

## Security

- JWT verification: JWKS (ES256/RS256) or HS256 secret (dev)
- Tenant id from verified `app_metadata` only
- Service role key backend-only; never in frontend
- Production startup rejects `MOCK_LLM`, `GEMINI_OFFLINE`, open CORS
