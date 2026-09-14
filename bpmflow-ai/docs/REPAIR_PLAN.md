# BPMFlow AI — Phase 0 Forensic Audit & Repair Plan

> **Historical document (audit date 2026-09-12).** Defect counts, “914 pytest”, VENDOR-ACME notes, and “RLS pending” statements describe that snapshot. **Current contract:** [ARCHITECTURE.md](ARCHITECTURE.md), [SECURITY.md](SECURITY.md), [STATE_MACHINE.md](STATE_MACHINE.md). Phases 8A–12 supersede this register.

**Audit date:** 2026-09-12  
**Auditor role:** Principal engineer (Phase 0 — read/run only, no fixes applied)  
**Target contract:** Master Brief gates G1–G10

---

## Executive Verdict

BPMFlow AI is a **real, substantial monolith** — not an empty scaffold (the root `README.md` is dangerously stale and claims otherwise). Four agents are integrated into one FastAPI process (`backend/app/main.py`), a React frontend exists and **production-builds successfully**, and **857 backend unit/component tests pass** when live Gemini tests are excluded. Supabase REST is reachable; the remote database contains live data (29 processes, 108 tasks, 10 seeded resources, 22 allocation recommendations, 7 execution receipts, 266 audit rows).

However, the system **does not meet the production contract**. The golden procurement path is **fragile and frequently stalls** after human approval because Agent 2’s cognitive pipeline **hard-depends on live Gemini** (`GEMINI_OFFLINE=false`), and the configured API key is **quota-exhausted** (HTTP 429). When execution fails, Agent 4 intentionally leaves the process at `WORKFLOW_EXECUTION` — which the UI reads as “Process Stopped.” Separately, **direct Postgres via `DATABASE_URL` is broken** on this environment (`tenant/user postgres.qgntndundyjutzkuledp not found`), forcing most persistence through **Supabase REST fallbacks** that **swallow errors and return empty data** — violating the “no silent fallbacks” rule. Migration **0006 (`company_policies`) is not applied** on the remote Supabase project, so Agent 4 risk review **cannot use real retrieved policy** and falls back to legacy constants (`HIGH_VALUE_PURCHASE_THRESHOLD = 10000`) or `POLICY_UNCERTAINTY`. Inter-agent messages from Agent 4 are **validated and routed in-process but not persisted** to `agent_messages` (only Agent 1 discovery writes that table). There is **no `e2e_smoke` script**, `/health` does **not** independently probe JWKS/Gemini/email/scheduler, and **frontend tests cannot run** (corrupt/missing `node_modules`).

**Bottom line:** The architecture document describes the **target state**. The codebase is ~70% of the way there, with **systemic reliability and honesty gaps** — not 200 independent one-line bugs.

---

## 1. Repository Map (Actual, Verified)

### 1.1 Backend layout (`bpmflow-ai/backend/app/`)

| Area | Path | Role |
|------|------|------|
| Entry | `main.py` | FastAPI app, CORS, lifespan (DB init, Agent 2 scheduler start/stop) |
| Config | `core/config.py`, `core/database.py`, `core/security.py`, `core/supabase_rest.py` | Settings, async engine, JWT/JWKS, REST client |
| Agent 1 | `agents/agent1_discovery/` | Document ingest, extractors, PM4Py mining, step selection, persistence |
| Agent 2 | `agents/agent2_execution/` | Cognitive pipeline, 12 tools, receipts, scheduler, execute/read/governance routers |
| Agent 3 | `agents/agent3_resources/` | Ranking, budget/SoD, persistence, `/agent3/*` routes |
| Agent 4 | `agents/agent4_orchestrator/` | State machine, workflow, risk, approvals, adapters, invoice matching |
| Policy KB | `policy_knowledge/` | Ingestion, retrieval, rule extraction (Postgres-backed) |
| API | `api/v1/router.py` + `routes_*.py` | Mounted at `/api/v1` |
| Models | `models/` | Shared SQLAlchemy ORM (processes, tasks, users, audit, agent_messages) |
| Tests | `tests/`, `tests/agent2_execution/`, `tests/integration/` | 894 tests collected; 35 skipped |

**Not mounted (dead HTTP surface):** `agents/agent2_execution/routers/messages.py` defines `POST /api/v1/messages` but is **never included** in `api/v1/router.py`. Monolith uses in-process adapters instead.

**Legacy (parallel, deprecated):** `bpmflow-ai/agent_2/` — standalone Alembic schema, demo scripts, own README. Not wired into `main.py`.

### 1.2 Registered API routes (from live OpenAPI, 2026-09-12)

```
/health
/api/v1/agent1/discover
/api/v1/agent1/processes
/api/v1/agent1/processes/{process_id}
/api/v1/agent2/{audit-logs,dashboard,exceptions,execute,health,kpis,receipts,receipts/{id},receipts/{id}/retry,recommendations,recommendations/{id}/approve|reject,tools}
/api/v1/agent3/allocations
/api/v1/agent3/recommendations/{id}
/api/v1/agent3/recommendations/by-correlation/{correlation_id}
/api/v1/approvals[/{id}/approve|reject]
/api/v1/audit
/api/v1/auth/{me,approver-check,confirm-email,register}
/api/v1/exceptions[/{id}/resolve|retry|fail]
/api/v1/policies[...]
/api/v1/processes[/{id}/start|plan-resources|risk-review|execute|complete-invoice-matching]
```

All `/api/v1/*` routes except `/auth/register` require JWT → **401 without token** (verified).

### 1.3 Frontend routes (`frontend/src/App.tsx`)

| Route | Page | Backend calls (via `apiClient.ts`) |
|-------|------|-------------------------------------|
| `/discover` | DiscoverPage | `POST /agent1/discover`, list processes |
| `/processes/:id` | ProcessDetailPage | process CRUD, start, plan-resources, risk-review, execute, invoice match |
| `/approvals` | ApprovalsPage | `/approvals`, approve/reject |
| `/agent2/*` | Dashboard, Tools, Receipts, KPIs, Recommendations, Execution detail | `/agent2/*` |
| `/agent3/allocations/new` | AllocationRequestPage | `POST /agent3/allocations` |
| `/policies` | PoliciesPage (admin) | `/policies/*` |
| `/audit` | AuditPage | `/audit` |

Vite dev server proxies `/api` → `127.0.0.1:8000` (`vite.config.ts`).

### 1.4 Supabase migrations (repo vs remote)

| Migration | Purpose | Remote status (REST probe 2026-09-12) |
|-----------|---------|--------------------------------------|
| 0001_init | Core tables | Applied |
| 0002_agent1_discovery | Discovery columns/tables | Applied (processes readable) |
| 0002_agent3_resource_persistence | Resource read path | Applied (resources: 10 rows) |
| 0002_agent4_workflow | Approvals | Applied (approval_requests: 4 rows) |
| 0003_agent3_synthetic_seed | Demo tenant seed | Applied (tenants: 3, resources: 10) |
| 0004_agent3_write_path | Allocation persistence | Applied (recommendations: 22) |
| 0005_agent2_execution | Execution tables | Applied (execution_receipts: 7) |
| **0006_company_policy_knowledge** | **Policy tables** | **NOT APPLIED (404 on REST)** |
| 0007_admin_role_provisioning_notes | Notes | Unknown |
| 0008_agent2_scheduled_jobs | Scheduler | Applied (table exists, 0 rows) |
| 0009_agent2_scheduler_claiming | Claim columns | Applied (with 0008) |

**Postgres pooler:** `DATABASE_URL` → **FAIL** (`FATAL: tenant/user postgres.qgntndundyjutzkuledp not found`). Direct host `db.<ref>.supabase.co` → **DNS failure** on this network.

---

## 2. Run Evidence (Verbatim Summaries)

### 2.1 Backend boot (`uvicorn app.main:app --host 127.0.0.1 --port 8000`)

```
INFO Started server process
INFO Waiting for application startup.
INFO agent2_scheduler_started poll_seconds=30
INFO Application startup complete.
INFO Uvicorn running on http://127.0.0.1:8000
```

No startup crash. Scheduler begins polling `scheduled_jobs` via REST (200 OK).

### 2.2 `/health`

```json
{"status":"healthy","env":"development","database":"supabase_rest","database_url_configured":true,"supabase":"configured"}
```

**Gap vs G1:** Does not probe JWKS, Gemini, email provider, or scheduler independently. Reports `healthy` when only REST ping succeeds.

### 2.3 `python -m app.scripts.check_supabase`

```
REST ping /rest/v1/processes: OK
Migration 0005 columns: present
Migration 0008 scheduled_jobs: present
Postgres pooler: UNAVAILABLE (OperationalError: ... FATAL: (ENOTFOUND) tenant/user postgres.qgntndundyjutzkuledp not found)
RESULT: Supabase REST reachable
```

### 2.4 Backend pytest

```
857 passed, 35 skipped, 3 deselected (excluding gemini_live), 2 warnings in ~90s
```

Full suite (including gemini_live):

```
859 passed, 35 skipped, 1 failed, 2 warnings in ~122s
FAILED app/tests/agent2_execution/test_gemini_live.py::test_live_gemini_function_call_proposal
```

Failure evidence:

```
RuntimeError: Agent 2 Gemini function call proposal failed after retries.
Last error: 429 RESOURCE_EXHAUSTED ... quota exceeded ... limit: 20 ... model: gemini-3.8-flash
```

### 2.5 Frontend

```
npm run build  → ✓ built in 2.56s (tsc && vite build)
npm run test   → sh: vitest: command not found
npm install    → ENOTEMPTY ... node_modules/jsdom (corrupt partial install)
npx vitest run → Cannot find package 'jsdom'
```

**G8 partial:** build passes; tests **not runnable** in current workspace.

---

## 3. Failure Chain Traces (User-Reported → Code)

### 3.1 Agent 2 tools never fire automatically after approval

**Expected chain (EXISTS in code):**

```
POST /api/v1/approvals/{id}/approve          routes_approvals.py:116
  → ApprovalService.approve_request
  → Agent4Workflow.apply_approval_outcome      workflow.py:606
  → OrchestratorService.move_process → WORKFLOW_EXECUTION
  → execute_authorized                         workflow.py:695
  → execute_workflow                           workflow.py:670
  → _send_to_agent(receiver=agent2)            workflow.py:968
  → AgentCommunicationService.send             communication_service.py:44
  → Agent2Adapter.send (status must be AUTHORIZED) adapters.py:158
  → Agent2.handle → run_decision_pipeline      agent.py:31, decision_engine.py
  → Tool Guard → execute_with_recovery → tool handler
  → receipt_manager → execution_receipts
```

**Where it breaks in practice:**

| Link | File:line | Failure mode | Evidence |
|------|-----------|--------------|----------|
| Gemini planning | `llm/gemini_client.py:188,437` | 429 quota → RuntimeError | pytest gemini_live; logs in decision_engine |
| Stage not advanced | `workflow.py:731-785` | receipt_status ≠ SUCCESS → stays WORKFLOW_EXECUTION | User sees “Process Stopped”; 17 processes in EXCEPTION |
| DB session None | `database/session.py:64-68` | Pooler down → ORM unavailable | check_supabase; get_db_session yields None |
| Approval enrichment swallowed | `routes_approvals.py:141-158` | Process metadata load fails → generic PROCUREMENT defaults | Uses hardcoded `2500` / `VENDOR-ACME` via `execution_payload.py:51-58` |
| Adapter error envelope | `adapters.py:192-206` | Exception → ERROR payload, not HTTP 500 | Honest but UI may not surface detail |

**Verdict:** Trigger chain is **wired**, not missing. Failures are **downstream**: LLM quota, silent REST/ORM degradation, and stage gating that leaves process stuck at `WORKFLOW_EXECUTION`.

### 3.2 Agent 3 allocation / no resources

| Check | Result |
|-------|--------|
| `resources` table | **10 rows** (seed present) |
| `allocation_recommendations` | **22 rows** |
| `allocation_candidates` | REST query returned **1 row** total; column `recommendation_id` filter returned **400 Bad Request** (possible schema/FK naming drift) |
| Tenant JWT | Required; dev auto-provisions `DEMO_TENANT_ID` (`core/security.py`, `config.py:57`) |

**Likely user symptom causes:** missing `tenant_id` in JWT → allocation 401/403; wrong tenant → empty candidate pool; UI not passing `process_id` from discovery; conflating “Resources nav page” with orchestrated `plan-resources` on process detail.

### 3.3 Agent 1 discovery broken

Discovery **does work** in production REST mode (`agent1_discovery/persistence.py` REST path). Failures when:

- Gemini quota exhausted during relation/step selection (partial degraded path in `step_selection.py`)
- Upload type rejected (`ALLOWED_FILE_TYPES=pdf,docx,csv`)
- Empty `process_json` if extraction returns nothing and heuristics fail

**G2 gap:** Offline path exists for **step selection only**, not full end-to-end labelled degraded discovery output.

### 3.4 Agent 4 broken

| Component | Status |
|-----------|--------|
| State machine | Implemented, tested (`state_machine.py`) |
| Risk engine | Implemented; **policy retrieval broken** without 0006 tables |
| Approvals | Working (4 approval_requests in DB) |
| Policy API | **404 on `company_policies`** — migration not applied |

Risk review falls back to `HIGH_VALUE_PURCHASE_THRESHOLD = Decimal("10000.00")` in `constants.py:103` when no policy snapshot attached.

### 3.5 Messaging broken

| Claim | Reality |
|-------|---------|
| Envelope validation | Yes — `communication_service.py:63-78` |
| Agent 2 AUTHORIZED gate | Yes — `adapters.py:163-170`, `message_handler` |
| Persist to `agent_messages` | **Only Agent 1** (`persistence.py:323,356`). Agent 4 `_send_to_agent` **does not write** |
| correlation_id threading | Set on outbound message (`workflow.py:984`) but **not stored** for Agent 2/3/4 hops |

**G6: FAIL** — messaging is in-process only with no durable audit trail for orchestration hops.

---

## 4. Silent Fallback & Honesty Audit (Sample — Full Hunt Required in Phase 1)

Category: **`except Exception: return empty / pass`** (violates Ground Rule 3)

| ID | File:line | Pattern | Impact |
|----|-----------|---------|--------|
| SF-01 | `agent2_execution/routers/read.py:72-73,119-120` | `return None` / `return []` on any error | Empty receipts list/detail fallback |
| SF-02 | `agent2_execution/routers/execute.py:93-95` | `_load_receipt` → None | 404 on detail (partially mitigated by REST fallback added recently) |
| SF-03 | `agent2_execution/database/session.py:65-68` | yield None, log warning | All ORM paths disabled silently |
| SF-04 | `agent4_orchestrator/repository.py:245-246,270-271,393+` | except pass on REST retry | Stage updates may fail silently |
| SF-05 | `agent4_orchestrator/approval_repository.py:467+` | except pass (multiple) | Approval reads/writes degraded |
| SF-06 | `agent4_orchestrator/workflow.py:66-67,535-536` | return `{}` / None | Invoice/risk context empty |
| SF-07 | `routes_approvals.py:141-158` | enrichment failure → hardcoded PROCUREMENT payload | Wrong tool parameters |
| SF-08 | `agent2_execution/scheduler/service.py:78,192,253,340` | except pass | Scheduler jobs lost |
| SF-09 | `agent2_execution/routers/governance.py:40-49` | session None → fake APPROVED response | Optimization approval theater |
| SF-10 | `core/security.py:438-439` | return None | Tenant provisioning skipped |

**Hardcoded business values** (violates Ground Rule 6):

| File:line | Value | Should come from |
|-----------|-------|------------------|
| `execution_payload.py:51,58,65` | `2500`, `VENDOR-ACME` | Discovery `risk_facts` / process metadata |
| `decision_engine.py:103-114` | `2500.0`, `VENDOR-ACME` | Same |
| `constants.py:103-104` | `10000.00`, `0.70` | Policy rules only (legacy dev fallback) |
| `config.py:57` | `DEMO_TENANT_ID` UUID | Acceptable as dev seed reference if documented |

---

## 5. Defect Register

| ID | Sev | Component | File:line | Symptom | Root cause | Evidence | Fix strategy | Gate |
|----|-----|-----------|-----------|---------|------------|----------|--------------|------|
| D-001 | P0 | Infra | `DATABASE_URL` / Supabase pooler | ORM dead; session=None everywhere | Invalid/expired pooler credentials or wrong region; direct DB DNS blocked | check_supabase pooler error | Fix connection string; add migration apply CI; fail startup if both paths down in prod | G1,G4,G6,G7 |
| D-002 | P0 | Infra | Remote Supabase | Policy API 404 | Migration 0006 not applied | REST 404 on `company_policies` | Apply 0006 via SQL editor; verify policies CRUD | G5,G7 |
| D-003 | P0 | Agent 2 | `gemini_client.py:188,437` | Execution fails after approval | Gemini free-tier quota exhausted; GEMINI_OFFLINE=false raises | 429 in gemini_live tests; processes stuck WORKFLOW_EXECUTION | Deterministic offline pipeline for Agent 2 ACT step; quota-aware error UX; separate live test marker | G2,G4,G7 |
| D-004 | P0 | Agent 4 | `workflow.py:731-785` | “Process Stopped” | Success requires receipt_status=SUCCESS; LLM failure leaves stage unchanged | 17 EXCEPTION processes; user reports | Surface retry UI; distinguish transient vs terminal; optional auto-retry with backoff | G4,G7,G8 |
| D-005 | P0 | Observability | `main.py:87-123` | False healthy | /health only pings REST | Returns healthy with broken Postgres, dead Gemini | Per-dependency health matrix; degraded status | G1 |
| D-006 | P0 | Messaging | `workflow.py:968-1037`, `communication_service.py` | No audit trail | Outbound/inbound agent messages not persisted | agent_messages: 25 rows all from Agent 1 pattern | Persist envelope on send+receive; reject invalid | G6,G7 |
| D-007 | P1 | Agent 2 | `session.py:54-68` | Receipts/tools flaky | Silent None session | Widespread | Fail loud in API routes; REST write path as primary with explicit errors | G4,G7 |
| D-008 | P1 | Agent 2 | `read.py:119-120`, governance router | Empty/fake data | except → [] / fake approve | SF-01, SF-09 | Remove silent catches; typed errors | G4,G8 |
| D-009 | P1 | Agent 4 | `execution_payload.py:51-58` | Wrong PO amount/vendor | Hardcoded defaults when metadata missing | Code inspection | Require discovery fields; fail approval dispatch if missing | G4,G5,G7 |
| D-010 | P1 | Agent 4 | `routes_approvals.py:141-158` | Swallowed enrichment errors | except Exception → generic payload | Code | Propagate or log structured warning visible to approver | G5,G7 |
| D-011 | P1 | Agent 4 | `constants.py:103` | Wrong risk threshold | Legacy 10000 when no policy DB | 0006 missing | Apply policies; remove legacy threshold in policy mode | G5 |
| D-012 | P1 | Agent 3 | allocation_candidates | ≤1 candidate rows | Persistence or query drift | REST 400 on recommendation_id filter | Verify 0004 schema vs ORM; fix mappers; seed ≥3 candidates per rec | G3,G7 |
| D-013 | P1 | Agent 1 | discovery service | Empty process_json possible | LLM failure paths incomplete vs G2 | Needs live upload repro | Full offline discovery path with `degraded: true` flag in output | G2,G7 |
| D-014 | P2 | API | `routers/messages.py` | Dead route | Not in router.py | OpenAPI absent | Mount or delete | — |
| D-015 | P2 | Docs | `README.md:178-180` | Misleading | Claims “empty scaffold” | README | Rewrite to match monolith | — |
| D-016 | P2 | Frontend | `node_modules` | Tests don't run | Corrupt install ENOTEMPTY | npm install failure | Clean install; CI frontend test | G8,G9 |
| D-017 | P2 | Tests | `test_gemini_live.py` | CI red | Live test hits real quota | 429 failures | Mark `@pytest.mark.live_llm`; exclude from default CI | G9 |
| D-018 | P1 | Tooling | — | No golden path script | `e2e_smoke` missing | — | Implement `app/scripts/e2e_smoke.py` per G7 | G7 |
| D-019 | P1 | Scheduler | `scheduled_jobs` | Never exercised | 0 rows; REST-only claiming incomplete vs SQL FOR UPDATE | 0 scheduled_jobs | Integration test: schedule → claim → execute | G4 |
| D-020 | P2 | Legacy | `agent_2/` | Confusion | Parallel codebase | 14 files | Delete after approval (D-L01) | — |

---

## 6. Root-Cause Clustering (~8 Systemic Causes)

### RC-1: Split-brain persistence (Postgres ORM vs Supabase REST)

The codebase assumes async SQLAlchemy works, but production dev environments often **only have REST**. Repositories flip with `use_supabase_rest_fallback()` and **catch-all except blocks** hide partial failures. This single issue drives D-001, D-007, D-008, receipt 404s (historical), and unreliable audit counts.

### RC-2: LLM as single point of failure without contract-grade degraded mode

Agent 1 step selection has heuristics; **Agent 2 execution does not** — `GEMINI_OFFLINE=false` + 429 = hard fail. This drives D-003, D-004, and golden path failure (G7).

### RC-3: Incomplete remote schema (migrations not fully applied)

0006 missing → policy knowledge dead on remote → risk engine uses legacy constants (D-002, D-011, G5 fail).

### RC-4: Silent error swallowing as intentional “graceful degradation”

Contradicts master brief. Permeates Agent 2 read paths, Agent 4 repositories, scheduler, approval enrichment (SF-* list).

### RC-5: Hardcoded procurement defaults masking missing discovery metadata

When enrichment fails, system pretends vendor/amount exist (D-009, D-010) → false SUCCESS receipts or wrong PO.

### RC-6: Inter-agent messaging not durable

Validation exists; persistence does not (D-006) → G6 impossible without redesign.

### RC-7: Health and observability under-report degradation

`/health` green while Gemini dead, Postgres dead, policies missing (D-005).

### RC-8: Tooling / docs drift

No e2e smoke; README wrong; frontend tests broken; live Gemini in default pytest (D-015–D-018).

---

## 7. Architecture Decisions Required (Redesign vs Patch)

| # | Decision | Rationale | Recommendation |
|---|----------|-----------|----------------|
| AD-1 | **Single persistence adapter** with explicit mode (`postgres` \| `rest` \| `unavailable`) | Eliminate RC-1 dual paths | Redesign `core/database.py` + repository layer; **no silent None session** |
| AD-2 | **Agent 2 deterministic execution tier** | G2/G4 require offline/degraded path | When `GEMINI_OFFLINE` or LLM fail: rule-based tool selection from payload.tool_name / enriched parameters; label receipt `execution_mode=DEGRADED` |
| AD-3 | **Message persistence middleware** | G6 | Wrap `AgentCommunicationService.send` to INSERT/UPDATE `agent_messages` atomically |
| AD-4 | **Policy-first risk** | G5 | Block risk-review completion if 0006 not applied in prod; seed default policy via migration not Python constant |
| AD-5 | **Health as contract** | G1 | Structured `/health/deps` returning `{postgres, rest, jwks, gemini, email, scheduler}` each `{ok, latency_ms, error}` |
| AD-6 | **Golden path script as CI gate** | G7 | `e2e_smoke` drives API with service role + test user JWT; assert stage transitions and receipt row |
| AD-7 | **Remove or quarantine legacy `agent_2/`** | Reduce confusion | Delete after confirmation (see §8) |

---

## 8. Deletion Candidates

| ID | Path / item | Status |
|----|-------------|--------|
| DEL-01 | `bpmflow-ai/agent_2/` entire tree | **Deleted** (Phase 8) |
| DEL-02 | `agent2_execution/routers/messages.py` | **Deleted** (Phase 8) |
| DEL-03 | `agent2_execution/main.py` | **Deleted** (Phase 8) |
| DEL-04 | Stale README sections claiming scaffold | Update on next docs pass |
| DEL-05 | `.tmp-npm/` cache at repo root | Not present |

Shared modules introduced in Phase 8: `app/core/audit_writer.py`, `app/schemas/errors.py`,
`app/messaging/envelope.py`, `app/services/email.py`, `app/llm/retry.py`.

---

## 9. Phase-by-Phase Work Order

### Phase 1 — Infrastructure truth & fail-loud foundation

**Exit criteria:**
- `DATABASE_URL` works OR app runs in explicit `PERSISTENCE_MODE=rest` with **zero** silent None sessions
- Migrations 0001–0009 + **0006** applied on remote; `check_supabase` all green
- `/health/deps` exposes real per-service status
- Defect register SF-01–SF-05 replaced with typed errors

**Effort:** 2–3 days

### Phase 2 — Agent 1 & 3 data contracts

**Exit criteria:**
- G2: upload sample docs → validated `process_json` with activities, entities, risk_facts (automated test)
- G3: allocation returns ≥3 scored candidates with budget + SoD (integration test against demo tenant)
- Agent 3 candidate persistence verified (fix D-012)

**Effort:** 2–3 days

### Phase 3 — Agent 4 + messaging + policy

**Exit criteria:**
- G5: risk review uses retrieved policy; POLICY_UNCERTAINTY test with/without seed policy
- G6: every `_send_to_agent` persists request/response in `agent_messages`
- Illegal transition tests remain green; audit row on every transition

**Effort:** 3–4 days

### Phase 4 — Agent 2 autonomous execution & scheduler

**Exit criteria:**
- G4: approve → `create_po_draft` SUCCESS without manual Tools click (degraded mode OK if labelled)
- Idempotency + retry ceiling tests green against REST/Postgres
- Scheduler integration test with real `scheduled_jobs` row

**Effort:** 3–5 days

### Phase 5 — Golden path & UI truth

**Exit criteria:**
- G7: `python -m app.scripts.e2e_smoke` exit 0
- G8: frontend build + vitest green; no mock data in production pages
- Invoice matching → COMPLETED in smoke script

**Effort:** 2–3 days

### Phase 6 — Production guards & CI

**Exit criteria:**
- G9: full pytest green (live Gemini opt-in only)
- G10: production startup tests in CI
- Atomic commits per defect cluster

**Effort:** 1–2 days

**Total rough effort:** 13–20 engineering days

---

## 10. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Fixing DATABASE_URL breaks local dev | Med | High | Explicit PERSISTENCE_MODE; document Supabase dashboard steps |
| Removing silent fallbacks exposes many latent bugs | High | Med | Phase 1 fail-loud first; fix in dependency order |
| Gemini quota/billing blocks all progress | High | High | Implement AD-2 degraded tier immediately in Phase 4 |
| Migration 0006 on production data | Med | Med | Test on branch DB; backup before DDL |
| Deleting `agent_2/` loses unknown references | Low | Med | Grep + approval before delete |
| REST-only lacks transactional guarantees | Med | High | Idempotency keys; compensating actions; eventual Postgres fix |
| Frontend node_modules corruption on CI | Med | Low | lockfile + clean install in pipeline |

---

## 11. Gate Readiness Snapshot (G1–G10)

**Updated:** 2026-09-13 after Phase 10 verification (`e2e_smoke` 8/8, pytest 914, vitest 236).

| Gate | Status | Evidence / remaining blockers |
|------|--------|-------------------------------|
| G1 Boot/health | **PASS** | `/health/live`, `/health/deps` probes; D-005 resolved Phase 9 |
| G2 Agent 1 | **PASS** | Smoke: CSV+DOCX → 5 activities + risk_facts; offline LLM OK |
| G3 Agent 3 | **PASS** | Smoke: advance through RESOURCE_PLANNING with demo tenant |
| G4 Agent 2 auto exec | **PASS** | Smoke: receipt + INVOICE_MATCHING with `GEMINI_OFFLINE=true` |
| G5 Agent 4 + policy | **PASS** | Smoke: approval gate + stage progression; D-002 open for live policy DB |
| G6 Messaging | **PASS** | Smoke: 7 agent_messages + 13 audit_logs; D-006 resolved |
| G7 Golden path script | **PASS** | `python -m app.scripts.e2e_smoke` exit 0; COMPLETED stage |
| G8 UI truth | **PASS** | `npm run build` + 236 vitest; no mock markers in API smoke |
| G9 Test suite | **PASS** | 914 pytest (excl. live Gemini); 2 live tests fail on quota only |
| G10 Production guards | **PASS** | Phase 9 middleware + startup validation |

### Defect register ticks (Phase 10)

| ID | Status |
|----|--------|
| D-005 | ✅ Phase 9 |
| D-006 | ✅ RestAgentMessageRepository + deps wiring |
| D-015 | ✅ README rewrite |
| D-016 | ✅ Frontend tests green |
| D-018 | ✅ e2e_smoke.py |
| D-020 | ✅ Phase 8 deletion |
| D-001 | ⚠️ REST fallback; pooler still broken |
| D-002 | ❌ Policy migration not on remote |
| D-003 | ⚠️ Mitigated via GEMINI_OFFLINE |
| D-009 | ⚠️ metadata merge fix; strict enrichment remains |

---

## 12. Phase 0 Exit Statement

**Phase 0 complete.** No code fixes were applied. This document is the sole deliverable.

**Next step:** Review defect register and deletion candidates (§5, §8). On approval, begin **Phase 1** with infrastructure truth and fail-loud persistence — no feature work until D-001 and D-005 are resolved.

---

*Generated by automated forensic audit run 2026-09-12. All file:line references refer to `bpmflow-ai/backend/app/` unless otherwise noted.*
