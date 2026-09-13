# BPMFlow AI — HTTP API

Base URL: `http://127.0.0.1:8000` (dev). OpenAPI: `/docs` · `/openapi.json`.

**Auth:** `Authorization: Bearer <supabase_access_token>` on all `/api/v1/*` except `POST /auth/register` (dev only).

## Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health/live` | Process alive |
| GET | `/health/ready` | Persistence + auth config ready |
| GET | `/health/deps` | Full probe matrix (postgres, rest, jwks, gemini, redis) |

## Auth

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET | `/api/v1/auth/me` | any | Current user profile |
| GET | `/api/v1/auth/approver-check` | approver, admin | RBAC probe |
| POST | `/api/v1/auth/register` | — | Dev: create confirmed user + profile |

## Agent 1 — Discovery

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/agent1/discover` | Multipart file upload; optional `process_id` |
| GET | `/api/v1/agent1/processes` | Recent discovered processes |
| GET | `/api/v1/agent1/processes/{id}` | Process detail + `process_json` |

## Processes & orchestration (Agent 4)

| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/api/v1/processes` | List / create |
| GET | `/api/v1/processes/{id}` | Process record + stage |
| POST | `/api/v1/processes/{id}/start` | Trigger discovery stage |
| POST | `/api/v1/processes/{id}/advance` | **Golden path driver** — autonomous stage chain |
| POST | `/api/v1/processes/{id}/plan-resources` | Agent 3 allocation |
| POST | `/api/v1/processes/{id}/risk-review` | Risk evaluation |
| POST | `/api/v1/processes/{id}/execute` | Manual Agent 2 dispatch |
| POST | `/api/v1/processes/{id}/complete-invoice-matching` | Invoice evidence → COMPLETED |

### Advance payload (key fields)

```json
{
  "idempotency_key": "unique-string",
  "max_steps": 8,
  "resource_planning": {
    "task_id": "uuid",
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "human_requirements": { "skills": ["python"] },
    "budget_requirements": { "amount": "5000", "currency": "USD" }
  },
  "invoice": {
    "invoice_number": "INV-001",
    "amount": 2500.0,
    "expected_invoice_number": "INV-001",
    "expected_amount": 2500.0
  }
}
```

## Approvals

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET | `/api/v1/approvals` | any | List approval requests |
| GET | `/api/v1/approvals/{id}` | any | Single approval |
| POST | `/api/v1/approvals/{id}/approve` | approver, admin | Approve + dispatch Agent 2 |
| POST | `/api/v1/approvals/{id}/reject` | approver, admin | Reject |

Approve requires discovery metadata (vendor, amount, currency, cost centre) on the process — returns 422 if missing.

## Agent 2

Prefix: `/api/v1/agent2/` — receipts, tools, execute, dashboard, KPIs, recommendations, exceptions, audit-logs.

## Agent 3

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/agent3/allocations` | Rank candidates (tenant JWT required) |
| GET | `/api/v1/agent3/recommendations/{id}` | Stored recommendation |
| GET | `/api/v1/agent3/recommendations/by-correlation/{correlation_id}` | Lookup by correlation |

## Policies & audit

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET/POST | `/api/v1/policies` | admin | Policy knowledge CRUD + upload |
| GET | `/api/v1/audit` | any | Audit log query (`entity_id`, `entity_type`) |

## Error shape

FastAPI default: `{"detail": "..."}` or validation errors array. Approval enrichment: `422` with `missing_fields`.
