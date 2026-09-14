# Security controls (as implemented)

## Authentication

Supabase JWTs verified via JWKS (preferred) or HS256 `SUPABASE_JWT_SECRET` in development. Missing/invalid/expired tokens → **401**. Identity (`sub`) maps to `public.users`.

## Tenant isolation

`tenant_id` is taken from verified JWT `app_metadata`, never as an authority field from JSON bodies. APIs 404/403 on cross-tenant process, audit, approval, procurement, and workflow plan access.

## RLS

Tenant-scoped tables enable RLS. **0024** drops world-readable `USING (true)` policies from early migrations and adds tenant policies for processes, audit_logs, approval_requests, execution_receipts, and related joins.

**Apply 0024 on Supabase before treating live RLS as complete.** The API uses the **service role**, which bypasses RLS; application filters remain mandatory.

**Never expose `SUPABASE_SERVICE_ROLE_KEY` to clients.** Frontend uses the anon key only.

## RBAC

Roles: `requester`, `approver`, `admin`.

Examples: approve/reject and exception resolve/retry/fail → approver/admin. Workflow **activate**, vendor create, tool register, demo seeds → privileged as implemented (activate = approver/admin; seeds/tools/vendors = admin).

## Tool Registry

`implementation_key` must be in the static allow-list (`app/tool_registry/implementations.py`). The database cannot import arbitrary modules.

## Human approval & Agent 4

Required high-risk paths stop at `AWAITING_HUMAN_APPROVAL`. Agent 2 cannot approve. Agent 4 owns `current_stage`.

## Agent 2 one-step

One WorkflowStep per request. Full-suite tool name forbidden.

## Audit & evidence

Mutations record audit rows. Evidence references resolve in-tenant. Document ingest: allow-listed types, size limits, path-traversal rejection.

## Production config

Startup `assert_production_config()`: no `MOCK_LLM`, no `DEBUG`, no `GEMINI_OFFLINE`, no `EMAIL_DRY_RUN`, real Gemini key, email configured, no wildcard CORS.

## Errors

Client errors are structured (`detail`). Production handlers avoid stack traces, SQL, and filesystem paths.
