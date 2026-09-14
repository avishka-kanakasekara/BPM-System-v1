# BPMFlow AI

Human-supervised multi-agent **Business Process Management** platform.

BPMFlow AI helps an organization **discover**, **model**, **allocate**, **approve**, **execute**, **monitor**, and **optimize** a business process — with humans remaining in control of approvals and TO-BE changes.

**Primary demo:** procurement / purchase-request lifecycle.

This is **not** a fully autonomous system. Agents propose and execute only within Agent 4’s state machine and human approval gates.

## Four agents

| Agent | Role |
|-------|------|
| **Agent 1** | Process discovery, document intelligence, hybrid IR (BM25 + vectors + fusion where implemented) |
| **Agent 2** | Authorized one-step workflow execution (RPA tools) and KPI / execution reporting |
| **Agent 3** | Workforce / resource allocation against the company directory |
| **Agent 4** | Orchestration, deterministic process state, risk gate, completion / exception |

## Lifecycle

```
DISCOVER → MODEL → ALLOCATE → APPROVE → EXECUTE → MONITOR → OPTIMIZE
```

Procurement example:

```
Purchase Request
  → Agent 1 discovery (evidence)
  → Agent 4 workflow plan (WorkflowPlan / WorkflowStep)
  → Agent 3 resource allocation
  → Human approval
  → Agent 2 one-step execution (purchase order)
  → Invoice record
  → Deterministic invoice matching
  → Agent 4 COMPLETED or EXCEPTION
  → Monitoring / KPI / TO-BE recommendation (human review)
```

## Quick start (local)

Verified commands (Windows PowerShell shown; Unix equivalents in [docs/SETUP.md](docs/SETUP.md)).

### Backend

```powershell
cd bpmflow-ai\backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Fill SUPABASE_* , DATABASE_URL , GEMINI_API_KEY (see backend/.env.example)
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- Liveness: `GET http://127.0.0.1:8000/health/live`
- Demo config (no secrets): `GET http://127.0.0.1:8000/health/demo`
- OpenAPI: `http://127.0.0.1:8000/docs`

Development LLM shortcuts (`MOCK_LLM=true`, `GEMINI_OFFLINE=true`) are **forbidden** when `ENV=production`.

### Frontend

Vite listens on **port 5174** (`frontend/vite.config.ts`) and proxies `/api` and `/health` to the API.

```powershell
cd bpmflow-ai\frontend
npm install
copy .env.example .env.local
# VITE_SUPABASE_URL + VITE_SUPABASE_ANON_KEY only — never the service role key
npm run dev
```

Open `http://localhost:5174`, sign in, then follow [docs/PROCUREMENT_DEMO.md](docs/PROCUREMENT_DEMO.md).

### Tests

```powershell
cd bpmflow-ai\backend
python -m pytest app/tests
```

**Verified Phase 12 baseline:** 1195 passed, 38 skipped, 0 failed. That number is a snapshot, not a permanent contract.

**Phase 13 regression:** 1196 passed, 38 skipped, 0 failed.

## Documentation

| Doc | Contents |
|-----|----------|
| [docs/SETUP.md](docs/SETUP.md) | Clone, env, Supabase migrations 0001–0024, run API/UI |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Runtime architecture (as implemented) |
| [docs/AGENTS.md](docs/AGENTS.md) | Agent responsibilities and boundaries |
| [docs/STATE_MACHINE.md](docs/STATE_MACHINE.md) | Process stages and allowed transitions |
| [docs/API.md](docs/API.md) | HTTP surface from source |
| [docs/API_EXAMPLES.md](docs/API_EXAMPLES.md) | Fictional request/response samples |
| [docs/PROCUREMENT_DEMO.md](docs/PROCUREMENT_DEMO.md) | PR-2026-0098 / PR-2026-0105 demo |
| [docs/DEMO_DATA.md](docs/DEMO_DATA.md) | Fictional seed data |
| [docs/SECURITY.md](docs/SECURITY.md) | Auth, RBAC, RLS, Tool Registry |
| [docs/RESPONSIBLE_AI.md](docs/RESPONSIBLE_AI.md) | Human-supervision model |
| [docs/TESTING.md](docs/TESTING.md) | How to run test slices |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common failures |
| [docs/PRODUCTION_CHECKLIST.md](docs/PRODUCTION_CHECKLIST.md) | Go-live checklist |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | Ops: health, pooler, smoke |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production env and migration notes |
| [docs/PERSISTENCE.md](docs/PERSISTENCE.md) | Postgres vs REST fallback |
| [docs/REPAIR_PLAN.md](docs/REPAIR_PLAN.md) | Historical Phase 0 audit (not current contract) |

## Layout

```
bpmflow-ai/
├── backend/app/          FastAPI monolith (agents 1–4)
├── frontend/src/         React / Vite UI
├── supabase/migrations/  SQL 0001 … 0024 (0024 = RLS hardening)
├── sample-documents/     Demo PDF/DOCX/CSV inputs
└── docs/
```

## Auth

Almost all `/api/v1/*` routes require `Authorization: Bearer <Supabase JWT>`. Roles: `requester`, `approver`, `admin`. Tenant comes from verified JWT `app_metadata.tenant_id`, not from the request body.

**Never** put `SUPABASE_SERVICE_ROLE_KEY` in the frontend.

## Demo seeds

Fictional **BPMFlow Demo Company** and vendors are loaded only when explicitly invoked (admin HTTP seed or documented scripts). They do **not** run at production startup. See [docs/DEMO_DATA.md](docs/DEMO_DATA.md).
