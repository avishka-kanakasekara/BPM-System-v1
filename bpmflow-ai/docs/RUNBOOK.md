# BPMFlow AI — Runbook

## Start / stop

```bash
cd bpmflow-ai/backend
# Windows: venv\Scripts\activate
source venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Development-only LLM shortcuts: `MOCK_LLM=true` and `GEMINI_OFFLINE=true` (forbidden when `ENV=production`).

Stop: `Ctrl+C` (drain + scheduler lease release).

Frontend: `cd frontend && npm run dev` → **http://localhost:5174**

## Health checks

```bash
curl -s http://127.0.0.1:8000/health/live
curl -s http://127.0.0.1:8000/health/demo
curl -s http://127.0.0.1:8000/health/deps
```

| Probe | OK when |
|-------|---------|
| `postgres` | Pooler reachable |
| `supabase_rest` | REST ping 200 |
| `jwks` | Keys fetched or HS256 secret configured |
| `gemini` | Configured, or skipped in offline/mock **development** |
| `/health/demo` | Lists migrations on disk including **0024**; never returns secrets |

## Migrations

```bash
python -m app.scripts.migration_status          # 0001–0012 runner set
python -m app.scripts.apply_pending_migrations  # 0001–0012 only
```

Apply **0013–0024** in Supabase SQL Editor. **0024 is required for live RLS.**

When pooler fails (`tenant/user … not found`): the **database password in `.env` is wrong or stale**, not a code bug.

```bash
python -m app.scripts.configure_database_url
```

Use the Session pooler URI from the dashboard (placeholder project ref only):

`postgresql://postgres.YOUR_PROJECT:PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres?sslmode=require`

## Seeds (explicit)

```bash
python -m app.scripts.seed_demo_tenant           # Agent 3 synthetic tenant ...0001
python -m app.scripts.seed_company_directory     # in-memory Demo Company ...d001; refused in production
```

Admin HTTP: `POST /api/v1/company/seed-demo`, `POST /api/v1/vendors/seed-demo`.

## Smoke / tests

Prefer `python -m pytest app/tests` (see [TESTING.md](TESTING.md)). Optional: `python -m app.scripts.e2e_smoke`.

## Common UI issues

| Symptom | Check |
|---------|--------|
| Blank UI on 5173 | Use port **5174** |
| Approve 403 | Role must be approver/admin |
| Activate 403 | Requester cannot activate plans |
| Matching never COMPLETED | Invoice must already exist; expected totals in JSON are ignored |
