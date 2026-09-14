# Production readiness checklist

## Security

- [ ] Authentication (JWT) on protected APIs
- [ ] RBAC (`requester` / `approver` / `admin`)
- [ ] RLS policies applied, including **migration 0024**
- [ ] Tenant isolation (JWT tenant; no body-as-authority)
- [ ] No hardcoded secrets; `.env` not committed
- [ ] Safe client errors (no stack traces / SQL)
- [ ] `SUPABASE_SERVICE_ROLE_KEY` backend-only

## Data

- [ ] Migrations 0001–0024 applied on the target database
- [ ] Constraints / unique keys (invoice number per tenant, PO uniqueness)
- [ ] Idempotent seeds and step execution keys
- [ ] Audit logs written for privileged actions

## Agents

- [ ] Agent 1 evidence-backed; does not set `current_stage`
- [ ] Agent 2 one-step; no full-workflow tool
- [ ] Agent 3 uses company directory
- [ ] Agent 4 deterministic state machine

## Procurement

- [ ] Vendor directory
- [ ] Quotations
- [ ] Purchase orders via authorized step
- [ ] Invoices persisted
- [ ] Deterministic matching
- [ ] Completion gate
- [ ] Exception path without unauthorized COMPLETED

## Monitoring

- [ ] Timeline
- [ ] KPI from persisted data
- [ ] Bottlenecks / exception analytics
- [ ] TO-BE generate + human review (no auto-activate)

## Deployment

- [ ] `ENV=production`
- [ ] `MOCK_LLM=false`
- [ ] `DEBUG=false`
- [ ] `GEMINI_OFFLINE=false`
- [ ] `EMAIL_DRY_RUN=false` + provider credentials
- [ ] Secrets in env / secret manager
- [ ] CORS explicit origins (no `*`)
- [ ] Migration **0024** applied
- [ ] Demo seed endpoints not used as startup
