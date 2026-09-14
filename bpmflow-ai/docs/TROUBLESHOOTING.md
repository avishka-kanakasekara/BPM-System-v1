# Troubleshooting

| Symptom | Interpretation | Next step |
|---------|----------------|-----------|
| Tables/policies missing; cross-tenant visible via PostgREST | Migrations 0013–**0024** not applied on the project | Apply SQL in Dashboard in order. **0024 is required for live RLS.** Python runner only covers 0001–0012. |
| 401 on `/api/v1/*` | Missing/invalid/expired JWT | Sign in again; check `SUPABASE_URL` / JWKS / `SUPABASE_JWT_SECRET` |
| 403 Tenant claim required | JWT has no `app_metadata.tenant_id` | Set tenant in Supabase user app_metadata (Admin API). Dev may map `DEMO_TENANT_ID`. |
| Startup error `MOCK_LLM cannot be enabled` | `ENV=production` | Disable MOCK_LLM or use `ENV=development` for local mock |
| Startup error `DEBUG cannot be enabled` | Production + DEBUG | Set `DEBUG=false` |
| Email / `EMAIL_DRY_RUN` production error | Production forbids dry-run | Configure SMTP/Resend and `EMAIL_DRY_RUN=false` |
| `/health/ready` 503 | Postgres and REST both failing | Fix `DATABASE_URL` password/pooler; `python -m app.scripts.configure_database_url` |
| Discovery “insufficient evidence” | Document empty, wrong type, or facts not in text | Use sample-documents; allowed types `pdf,docx,csv,txt` |
| Agent 3 no eligible resource | Directory empty or SoD/skill miss | Admin `POST /company/seed-demo`; check tenant id `...d001` |
| Tool not registered / UNKNOWN_IMPLEMENTATION | Allow-list mismatch or disabled tool | Seed registry in tests; admin register only allow-listed keys |
| PO before approval | Process not in `WORKFLOW_EXECUTION` or step waiting human | Approve first; Agent 2 cannot approve |
| Invoice mismatch / not COMPLETED | Amounts/qty/vendor/currency differ; or invoice never persisted | Inspect stored PO+invoice; matching ignores caller expected totals |
| Stuck in EXCEPTION | Open blocking exception | Approver resolve/retry/fail; recovery uses the state machine — resolve does not auto-complete |
| Frontend on 5173 empty | Vite is configured for **5174** | Use `http://localhost:5174` |
| Activate workflow 403 as requester | Activation is approver/admin | Sign in as approver |

Do not “fix” authorization by disabling JWT in production.
