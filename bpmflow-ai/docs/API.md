# BPMFlow AI — HTTP API

Base URL (dev): `http://127.0.0.1:8000`. OpenAPI: `/docs`, `/openapi.json`.

**Auth:** `Authorization: Bearer <supabase_access_token>` on `/api/v1/*` except `POST /api/v1/auth/register` (development). This list is taken from the routers under `backend/app/`; it does not invent endpoints.

## Health (unauthenticated)

| Method | Path |
|--------|------|
| GET | `/health/live` |
| GET | `/health/ready` |
| GET | `/health` and `/health/deps` |
| GET | `/health/demo` |
| GET | `/` |

## Auth — `/api/v1/auth`

| Method | Path | Notes |
|--------|------|--------|
| GET | `/me` | Current user |
| GET | `/approver-check` | approver, admin |
| POST | `/register` | Dev registration |
| POST | `/confirm-email` | Email confirm helper |

## Agent 1 — `/api/v1/agent1`

| Method | Path |
|--------|------|
| POST | `/discover` |
| GET | `/processes` |
| GET | `/processes/{process_id}` |
| POST | `/documents` |
| GET | `/documents/{document_id}` |
| POST | `/search` |
| GET | `/evidence/{chunk_id}` |

## Processes & orchestration — `/api/v1/processes`

| Method | Path |
|--------|------|
| GET, POST | `/` |
| GET | `/{process_id}` |
| POST | `/{process_id}/start` |
| POST | `/{process_id}/advance` |
| POST | `/{process_id}/plan-resources` |
| POST | `/{process_id}/risk-review` |
| POST | `/{process_id}/execute` |
| POST | `/{process_id}/complete-invoice-matching` |
| POST | `/{process_id}/workflow/plan` |
| GET | `/{process_id}/workflow` |
| GET | `/{process_id}/quotations` |
| GET | `/{process_id}/purchase-order` |
| GET | `/{process_id}/invoices` |
| GET | `/{process_id}/exceptions` |
| GET | `/{process_id}/monitoring` |
| GET | `/{process_id}/timeline` |
| GET | `/{process_id}/kpis` |
| POST | `/{process_id}/kpis/calculate` |
| GET | `/{process_id}/bottlenecks` |
| GET | `/{process_id}/exception-analytics` |
| GET | `/{process_id}/recommendations` |
| POST | `/{process_id}/recommendations/generate` |

`advance` chains **Agent 4** stages only. It still stops for human approval and invoice evidence. Caller `expected_*` amounts are not the invoice-match source of truth.

## Workflow plans — `/api/v1/workflows`

| Method | Path | Notes |
|--------|------|--------|
| POST | `/` | Create plan |
| GET | `/{workflow_plan_id}` | |
| GET | `/{workflow_plan_id}/steps` | |
| POST | `/{workflow_plan_id}/steps` | |
| POST | `/{workflow_plan_id}/validate` | |
| POST | `/{workflow_plan_id}/activate` | **approver or admin** |
| POST | `/{workflow_plan_id}/steps/{workflow_step_id}/execute` | Agent 2 one-step |

## Agent 2 — `/api/v1/agent2`

| Method | Path |
|--------|------|
| GET | `/health` |
| GET | `/tools` |
| GET | `/dashboard` |
| GET | `/receipts` |
| GET | `/receipts/{receipt_id}` |
| POST | `/receipts/{receipt_id}/retry` |
| POST | `/execute` |
| GET | `/kpis` |
| GET | `/recommendations` |
| POST | `/recommendations/{recommendation_id}/approve` |
| POST | `/recommendations/{recommendation_id}/reject` |
| GET | `/exceptions` |
| GET | `/audit-logs` |

`POST /execute` with `__full_task_suite__` returns 403.

## Agent 3 — `/api/v1/agent3`

| Method | Path |
|--------|------|
| POST | `/allocations` |
| GET | `/recommendations/{recommendation_id}` |
| GET | `/recommendations/by-correlation/{correlation_id}` |

## Approvals — `/api/v1/approvals`

| Method | Path | Roles |
|--------|------|--------|
| GET | `/` | authenticated |
| GET | `/{approval_id}` | authenticated |
| POST | `/{approval_id}/approve` | approver, admin |
| POST | `/{approval_id}/reject` | approver, admin |

## Exceptions — `/api/v1/exceptions`

| Method | Path | Roles |
|--------|------|--------|
| GET | `/` | authenticated |
| GET | `/{exception_id}` | authenticated |
| POST | `/{exception_id}/resolve` | approver, admin |
| POST | `/{exception_id}/retry` | approver, admin |
| POST | `/{exception_id}/fail` | approver, admin |

## Procurement

| Method | Path | Notes |
|--------|------|--------|
| GET | `/api/v1/vendors` | |
| GET | `/api/v1/vendors/{vendor_id}` | |
| POST | `/api/v1/vendors` | admin |
| POST | `/api/v1/vendors/seed-demo` | admin; not production |
| GET | `/api/v1/invoices/{invoice_id}` | |
| POST | `/api/v1/invoices` | admin; persist only, not MATCHED |

PO creation is **not** a public vendor route; it happens through authorized Agent 2 `CREATE_PURCHASE_ORDER`.

## Tools — `/api/v1/tools`

| Method | Path | Roles |
|--------|------|--------|
| GET | `/` | tenant user |
| POST | `/resolve` | tenant user |
| GET | `/{tool_id}` | tenant user |
| POST | `/` | admin |
| POST | `/{tool_id}/enable` | admin |
| POST | `/{tool_id}/disable` | admin |

## Company directory — `/api/v1/company`

| Method | Path | Notes |
|--------|------|--------|
| GET | `/employees`, `/employees/{id}` | |
| POST | `/employees` | admin |
| GET | `/departments`, `/roles`, `/approvers`, `/sod` | |
| POST | `/seed-demo` | admin; not production |

## Policies — `/api/v1/policies`

Admin policy knowledge CRUD, search, activate/archive versions.

## Audit — `/api/v1/audit`

`GET /` — tenant-filtered when JWT tenant is present.

## TO-BE recommendations (process-scoped)

| Method | Path | Notes |
|--------|------|--------|
| GET | `/api/v1/recommendations/{recommendation_id}` | |
| POST | `/api/v1/recommendations/{recommendation_id}/review` | approver/admin |

Generate via `POST /api/v1/processes/{id}/recommendations/generate`.
