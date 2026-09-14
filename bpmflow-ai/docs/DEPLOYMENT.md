# BPMFlow AI — Production Deployment

## Prerequisites

- Supabase project with migrations applied (see **Migration order**)
- Gemini API key with quota (Agent 1 + Agent 2)
- Email provider configured (Resend or SMTP) when `ENV=production`
- Frontend built with production API URL and Supabase anon key

## Required environment variables

| Variable | Production | Notes |
|----------|------------|-------|
| `ENV` | `production` | Enables production guards at startup |
| `DEBUG` | `false` | Startup fails if `true` |
| `SUPABASE_URL` | Required | Project API URL |
| `SUPABASE_ANON_KEY` | Required | Frontend only |
| `SUPABASE_SERVICE_ROLE_KEY` | Required | Backend only; never expose to browser |
| `DATABASE_URL` | Required* | Postgres URI (`sslmode=require` for Supabase) |
| `PERSISTENCE_MODE` | `auto` or `postgres` | `rest` only if Postgres unreachable |
| `GEMINI_API_KEY` | Required | No `MOCK_LLM` / `GEMINI_OFFLINE` in prod |
| `EMAIL_PROVIDER` | `resend` or `smtp` | `EMAIL_DRY_RUN=false` in prod |
| `EMAIL_FROM` | Required | Verified sender |
| `CORS_ORIGINS` | Explicit list | No `*`; include frontend origin(s) |

Optional tuning:

| Variable | Default | Purpose |
|----------|---------|---------|
| `RATE_LIMIT_AUTH_PER_MINUTE` | 20 | Auth POST rate limit per IP |
| `RATE_LIMIT_UPLOAD_PER_MINUTE` | 10 | Discovery upload rate limit per IP |
| `MAX_UPLOAD_MB` | 20 | Per-file upload cap |
| `MAX_REQUEST_MB` | 25 | Total request body cap |
| `EXTERNAL_HTTP_TIMEOUT_SECONDS` | 30 | Supabase REST, Resend, etc. |
| `SHUTDOWN_DRAIN_SECONDS` | 15 | Graceful shutdown wait |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | 5 / 10 | Direct Postgres only (not pooler) |

Copy `backend/.env.example` to `backend/.env` and fill values.

## Migration order

Apply `supabase/migrations/` **0001_init.sql** through **0024_phase12_rls_hardening.sql** in numeric order.

**0024 contains final RLS hardening.** Until it is applied on the Supabase project, live RLS is incomplete.

The helper `python -m app.scripts.apply_pending_migrations` auto-applies **0001–0012** only. Paste **0013–0024** in **Dashboard → SQL Editor**. This repo does not auto-migrate a remote database from API startup.

Check files on disk (no secrets): `GET /health/demo` after the API is running.

## Seeding (demo / staging)

```bash
cd bpmflow-ai/backend
python -m app.scripts.seed_demo_tenant
```

Requires `SUPABASE_SERVICE_ROLE_KEY` and applied migrations.

## Start the API

```bash
cd bpmflow-ai/backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Production startup runs `settings.assert_production_config()` — misconfiguration fails fast (G10).

## Smoke verification

1. **Liveness:** `GET /health/live` → `{"status":"alive"}`
2. **Readiness:** `GET /health/ready` → `status: ready` when persistence + auth OK
3. **Dependencies:** `GET /health/deps` → per-service probe report
4. **Auth:** Sign in via Supabase; `GET /api/v1/auth/me` with Bearer token
5. **Golden path (when available):** `python -m app.scripts.e2e_smoke`

Frontend:

```bash
cd bpmflow-ai/frontend
npm ci && npm run build && npm test
```

Backend G10 tests:

```bash
cd bpmflow-ai/backend
pytest app/tests/test_g10_production.py -q
```

## Rollback

1. **Application:** redeploy previous container/image or git tag; env vars unchanged unless schema changed.
2. **Database:** Supabase migrations are forward-only — restore from backup if a migration must be reversed.
3. **Scheduler:** on graceful shutdown the API releases `CLAIMED` jobs for this worker back to `PENDING`.
4. **Verify:** `/health/deps` and a read-only API call (`GET /api/v1/processes` with valid JWT).

## Graceful shutdown

On SIGTERM / uvicorn shutdown:

1. New requests receive `503` (except health probes)
2. In-flight requests drain up to `SHUTDOWN_DRAIN_SECONDS`
3. Agent 2 scheduler stops and releases job leases
4. DB engine and Agent 3 LLM clients close

## Security checklist

- [ ] `ENV=production`, `DEBUG=false`, no `MOCK_LLM`
- [ ] CORS locked to known frontend origins
- [ ] Rate limits enabled (defaults in config)
- [ ] Secrets only in env / secret manager — never in logs (see `test_g10_production.py`)
- [ ] Service role key server-side only
- [ ] Migration **0024** applied
