# BPMFlow AI — Runbook

## Start / stop

```bash
cd bpmflow-ai/backend
source venv/bin/activate
GEMINI_OFFLINE=true MOCK_LLM=true uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Stop gracefully: `Ctrl+C` (drains in-flight requests, releases scheduler leases).

Frontend: `cd frontend && npm run dev`

## Health checks

```bash
curl -s http://127.0.0.1:8000/health/live | jq .
curl -s http://127.0.0.1:8000/health/deps | jq .
```

| Probe | OK when |
|-------|---------|
| `postgres` | Pooler reachable |
| `supabase_rest` | REST ping 200 |
| `jwks` | Keys fetched or HS256 secret configured |
| `gemini` | Configured, or skipped in offline/mock mode |

`ready=false` with `supabase_rest=ok` is **acceptable** in REST-degraded dev.

## Migrations

```bash
python -m app.scripts.migration_status
python -m app.scripts.apply_pending_migrations   # needs working DATABASE_URL
python -m app.scripts.seed_demo_tenant
```

When pooler fails (`tenant/user … not found`): the **database password in `.env` is wrong or stale**, not a code bug.

```bash
python -m app.scripts.configure_database_url   # tests current URI, prints fix steps
```

**Fix pooler (5 minutes):**

1. [Supabase Dashboard](https://supabase.com/dashboard) → your project → **Project Settings → Database**
2. Click **Reset database password** and save the new password
3. **Connect** → **ORMs** → copy the **Session pooler** URI (port **5432**, user `postgres.<project-ref>`)
4. Test and write to `.env`:

```bash
DATABASE_URL='postgresql://postgres.qgntndundyjutzkuledp:NEW_PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres?sslmode=require' \
  python -m app.scripts.configure_database_url --write --url "$DATABASE_URL"
python -m app.scripts.apply_pending_migrations
```

If `db.<ref>.supabase.co` DNS fails on your Mac, use the **pooler URI only** or enable Supabase **IPv4 add-on**.

Paste pending SQL in SQL Editor when pooler is still broken:

- `0008_company_policy_knowledge.sql` — policy retrieval
- `0014_process_advancement.sql` — durable advance idempotency

Verify: `python -m app.scripts.check_supabase` (should show both tables **present**).

## E2E smoke

```bash
# Server already running:
GEMINI_OFFLINE=true MOCK_LLM=true python -m app.scripts.e2e_smoke

# Full cold start:
python -m app.scripts.e2e_smoke --cold-start
```

Auth resolution order:

1. `E2E_BEARER_TOKEN` / `E2E_APPROVER_TOKEN`
2. `SUPABASE_JWT_SECRET` + `E2E_USER_ID`
3. Dev register + password grant (`E2E_EMAIL`, `E2E_PASSWORD`, …)

## CI commands

```bash
pytest app/tests -q \
  --ignore=app/tests/integration \
  --ignore=app/tests/agent2_execution/test_gemini_live.py

ruff check app
cd ../frontend && npm run build && npm test
```

Mark live Gemini: `@pytest.mark.live_llm` — exclude from default CI.

## Common failures

| Symptom | Cause | Fix |
|---------|-------|-----|
| `/advance` 500, `process_advancement_runs` 404 | Migration 0014 not applied | Apply SQL or accept in-memory idempotency (logged warning) |
| Approve 422 enrichment | No discovery risk_facts on process | Re-run discover with sample DOCX |
| Process stuck at WORKFLOW_EXECUTION | Live Gemini quota | `GEMINI_OFFLINE=true` |
| Agent 3 403 tenant | JWT missing `app_metadata.tenant_id` | Register via dev `/auth/register` or set metadata in Supabase |
| Old server on :8000 | Stale uvicorn without `/health/live` | Kill process on 8000, restart current code |

## Logs

JSON structured logs to stdout. Every request gets `correlation_id` (header `X-Correlation-ID` or generated). Secrets redacted in formatter.

## Production

See [DEPLOYMENT.md](DEPLOYMENT.md). `ENV=production` forbids mock/offline LLM and validates CORS + email config at startup.
