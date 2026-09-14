# BPMFlow AI — architecture (as implemented)

BPMFlow AI is a **human-supervised multi-agent BPM** system. It is not fully autonomous.

**Last documentation pass:** Phase 13 (aligned with Phases 8A–12 code).

## Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 18 + Vite + TypeScript |
| Backend | Python FastAPI monolith (`backend/app/main.py`) |
| Database | Supabase / PostgreSQL |
| Auth | Supabase JWT (JWKS or HS256 secret in development) |
| IR | Tenant-scoped document corpus: BM25 + embeddings + hybrid fusion/reranking (`app/ir/`) |

```
Browser (Vite :5174)
    JWT (anon key only)
        │
        ▼
FastAPI :8000
    ├── Agent 1  discovery + document intelligence + IR ingest/search
    ├── Agent 2  one-step WorkflowStep execution + receipts + KPIs
    ├── Agent 3  resource ranking (company directory)
    ├── Agent 4  state machine, plans, approvals, completion gate
    ├── Tool Registry (allow-listed implementation keys)
    ├── Procurement (vendor, quotation, PO, invoice, match)
    ├── Exceptions + audit + monitoring + TO-BE recommendations
    └── Postgres and/or Supabase REST (service role — backend only)
```

## Responsibility boundaries

| Component | Owns | Does not own |
|-----------|------|----------------|
| **ProcessContext** | Canonical discovered facts for a process | Workflow stage |
| **WorkflowPlan / WorkflowStep** | Ordered authorized work | Automatic execution of the whole plan |
| **Tool Registry** | Resolve `required_action` → allow-listed implementation | Arbitrary Python imports or execution |
| **Agent 4 StateMachine** | `current_stage` transitions | LLM decisions |
| **Human** | Approval, exception resolve/fail, TO-BE review, plan activation (approver/admin) | Nothing required of agents without a gate |
| **Audit logs** | Who did what on which entity | Client-supplied actor impersonation |
| **Monitoring** | Observational KPIs / timeline | Invented durations or fake completion times |
| **TO-BE recommendations** | Evidence-backed suggestions | Auto-activation of plans |

## Persistence

Postgres is preferred. If the pooler is down, some repositories fall back to **Supabase REST with the service role**. That key must never ship to the browser.

Row Level Security (RLS) is defined in SQL. **Migration 0024** closes legacy `USING (true)` policies. Until 0024 is applied on the project, live RLS is incomplete. The backend still filters by JWT tenant on APIs.

## Frontend

Routes in `frontend/src/App.tsx`: dashboard, discover, processes, approvals, audit, policies (admin), Agent 2, Agent 3. Types can be regenerated with `npm run generate:api-types`.

## Security posture (summary)

JWT on `/api/v1/*` (except documented register). Roles `requester` / `approver` / `admin`. Tenant from `app_metadata`. Agent 2 executes **one** authorized WorkflowStep per request. Invoice matching is deterministic against persisted PO/invoice rows.
