# Local setup (no Docker)

Use the actual commands in this repository. Do not invent Docker or extra services.

## 1. Clone

```bash
git clone <your-fork-or-classroom-url>
cd BPM-System-v1/bpmflow-ai
```

## 2. Backend Python environment

```bash
cd backend
python -m venv venv
```

Windows: `venv\Scripts\activate`  
Unix: `source venv/bin/activate`

```bash
pip install -r requirements.txt
```

## 3. Environment variables

```bash
# Windows
copy .env.example .env
# Unix
cp .env.example .env
```

Fill at least:

| Category | Variables |
|----------|-----------|
| Database | `DATABASE_URL` |
| Supabase | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` |
| Auth | JWKS via `SUPABASE_URL` and/or `SUPABASE_JWT_SECRET` (dev HS256) |
| LLM | `GEMINI_API_KEY` (or `MOCK_LLM=true` **only** in development) |
| Email | `EMAIL_DRY_RUN=true` in development; live SMTP/Resend in production |
| Uploads | `ALLOWED_FILE_TYPES`, `MAX_UPLOAD_MB` |
| Runtime | `ENV=development`, `DEBUG=true` locally |

Never commit `.env`. Production (`ENV=production`) **fails at startup** if `MOCK_LLM=true` or `DEBUG=true`.

Frontend:

```bash
cd ../frontend
copy .env.example .env.local   # Windows
# cp .env.example .env.local   # Unix
```

Set `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` only.

## 4. Supabase migrations

SQL lives in `bpmflow-ai/supabase/migrations/` as **0001 … 0024**.

**0024 must be applied** on the Supabase project before live RLS hardening is complete.

The Python helper `python -m app.scripts.apply_pending_migrations` only auto-applies **0001–0012** (naive SQL splitter). Apply **0013–0024** in **Supabase Dashboard → SQL Editor**, in numeric order, one file at a time.

Check what is on disk (does not apply SQL, does not print secrets):

```bash
cd backend
# with API running:
# GET http://127.0.0.1:8000/health/demo
python -m app.scripts.migration_status
```

`migration_status` reports the Python runner set (0001–0012). Treat 0013–0024 as dashboard-applied even if the runner says “complete”.

This repository **does not** automatically run migrations against a remote database from the API process.

## 5. Start FastAPI

From `bpmflow-ai/backend` with the venv active:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Optional development LLM:

```bash
# Unix
MOCK_LLM=true GEMINI_OFFLINE=true uvicorn app.main:app --host 127.0.0.1 --port 8000
```

PowerShell:

```powershell
$env:MOCK_LLM="true"; $env:GEMINI_OFFLINE="true"; uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 6. Start React

From `bpmflow-ai/frontend`:

```bash
npm install
npm run dev
```

UI: **http://localhost:5174** (configured in `vite.config.ts`). `/api` is proxied to `:8000`.

## 7. Authenticate

1. Open the UI → Sign up / Sign in (Supabase Auth).
2. Dev registration: `POST /api/v1/auth/register` (see OpenAPI `/docs`).
3. Confirm JWT `app_metadata.tenant_id` for tenant-scoped APIs.

Roles: `requester` | `approver` | `admin`.

## 8. Run the demo

1. As **admin**, seed fictional directory/vendors if empty:
   - `POST /api/v1/company/seed-demo`
   - `POST /api/v1/vendors/seed-demo`  
   (blocked when `ENV=production` and `DEBUG` is false)
2. Follow [PROCUREMENT_DEMO.md](PROCUREMENT_DEMO.md).

## 9. Health

| Path | Meaning |
|------|---------|
| `GET /health/live` | Process up |
| `GET /health/ready` | Persistence + auth usable |
| `GET /health/deps` | Probes (postgres, REST, JWKS, Gemini, Redis) |
| `GET /health/demo` | Flags + migration files on disk; **no secrets**; does not seed |

## Frontend contract (no redesign)

The current UI can: authenticate, list/create processes, open process detail (stage + actions), Discover upload, approvals, Agent 2 dashboard/receipts/KPIs, Agent 3 allocation pages, audit, admin policies.

**Known limitations**

- Vite port is **5174**, not 5173.
- Exception URLs `/exceptions/:id` redirect to `/processes`.
- Process monitoring / TO-BE APIs exist on the backend; the UI mainly shows Agent 2 KPIs/optimizations, not a dedicated TO-BE review screen. Use OpenAPI or curl for ` /processes/{id}/monitoring` and `/recommendations/{id}/review`.
- `POST /processes/{id}/advance` still exists as a convenience chain of **Agent 4-owned** stages; it is not unrestricted autopilot (human approval and invoice evidence still stop the chain).
