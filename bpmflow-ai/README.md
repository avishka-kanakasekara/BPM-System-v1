# BPMFlow AI

Four-agent, human-supervised BPM platform: discovery (Agent 1), execution (Agent 2), resource allocation (Agent 3), and orchestration/risk (Agent 4). One FastAPI monolith at `backend/app/main.py` and a React/Vite frontend at `frontend/`.

## Quick start (verified 2026-09-13)

### 1. Backend

```bash
cd bpmflow-ai/backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # fill SUPABASE_* , DATABASE_URL , GEMINI_API_KEY
```

Required env (see `backend/.env.example`):

| Variable | Purpose |
|----------|---------|
| `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` | Auth + REST persistence |
| `DATABASE_URL` | Postgres pooler (preferred); REST fallback when pooler fails |
| `GEMINI_API_KEY` | Live LLM; set `GEMINI_OFFLINE=true` for deterministic smoke/tests |
| `DEMO_TENANT_ID` | Demo tenant UUID for Agent 3 (`00000000-0000-0000-0000-000000000001`) |

Apply migrations (when pooler works):

```bash
python -m app.scripts.apply_pending_migrations
python -m app.scripts.seed_demo_tenant
python -m app.scripts.migration_status
```

Start API:

```bash
GEMINI_OFFLINE=true MOCK_LLM=true uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Health: `GET http://127.0.0.1:8000/health/live` · OpenAPI: `/docs`

### 2. Frontend

```bash
cd bpmflow-ai/frontend
npm install
cp .env.example .env.local        # VITE_SUPABASE_URL + VITE_SUPABASE_ANON_KEY
npm run dev                       # http://localhost:5173 , proxies /api → :8000
```

### 3. E2E smoke (golden path G1–G8)

With the API running:

```bash
cd bpmflow-ai/backend
GEMINI_OFFLINE=true MOCK_LLM=true python -m app.scripts.e2e_smoke
```

Cold start (migrate + seed + start server + smoke):

```bash
python -m app.scripts.e2e_smoke --cold-start
```

Exit code 0 = all gates passed. See `docs/RUNBOOK.md` for troubleshooting.

## Verification commands

```bash
# Backend (exclude live Gemini quota tests)
cd backend && pytest app/tests -q \
  --ignore=app/tests/integration \
  --ignore=app/tests/agent2_execution/test_gemini_live.py

ruff check app
mypy app/core/audit_writer.py app/core/middleware.py  # scoped; see pyproject.toml

# Frontend
cd frontend && npm run build && npm test
```

Latest run: **914 pytest passed**, **236 Vitest passed**, **e2e_smoke 8/8**.

## Project layout

```
bpmflow-ai/
├── backend/app/          # FastAPI monolith (agents 1–4, policy KB, API)
├── frontend/src/         # React UI (discover, process cockpit, approvals, agent2/3)
├── supabase/migrations/  # SQL migrations 0001–0014
├── sample-documents/     # Procurement CSV + DOCX for discovery demo
└── docs/                 # ARCHITECTURE, API, RUNBOOK, DEMO_SCRIPT, REPAIR_PLAN
```

## Documentation

| Doc | Contents |
|-----|----------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Runtime architecture (as implemented) |
| [docs/API.md](docs/API.md) | HTTP surface summary |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | Ops, health, migrations, smoke |
| [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) | Procurement UI click path |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production guards |
| [docs/REPAIR_PLAN.md](docs/REPAIR_PLAN.md) | Defect register + gate status |
| [docs/CHANGELOG_REPAIR.md](docs/CHANGELOG_REPAIR.md) | Defect resolutions |

## Auth

All `/api/v1/*` routes except `POST /auth/register` require a Supabase JWT (`Authorization: Bearer …`). Development registration auto-confirms email and provisions `public.users` role (`requester` | `approver` | `admin`).
