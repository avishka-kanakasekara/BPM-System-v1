# CLAUDE.md — Agent 2: Intelligent Workflow Execution, RPA & Process Optimization

> **SUPERSEDED for runtime.** Agent 2 now runs inside the FastAPI monolith at
> `bpmflow-ai/backend/app/agents/agent2_execution`. Do not start this directory
> as its own server; `mock_agent4/` is gone. Use `bpmflow-ai/backend/.env`.
> Historical design notes below remain useful; where they conflict with the
> monolith (separate SQLite, port 8002, mock Agent 4), the monolith wins.

> **Read this file before doing anything else in this repo, every session.**

---

## What Agent 2 Is

Agent 2 is a **bounded-autonomy LLM agent** — not a rules engine and not fully autonomous. It receives authorized tasks from Agent 4 (the Orchestrator), plans execution using Google Gemini, executes through approved tools only, observes outcomes, diagnoses failures, recovers safely, records evidence of every action, and produces evidence-based optimization recommendations. It occupies a deliberate middle ground: intelligent enough to reason about *how* to execute a task, constrained enough that it can never exceed its mandate.

---

## The 11-Step Cognitive Cycle

Every task Agent 2 handles follows this cycle:

1. **PERCEIVE** — receive a task assignment and its context.
2. **UNDERSTAND** — parse the task, identify requirements, constraints, and SLAs.
3. **REASON** — determine the best approach given current state and history.
4. **PLAN** — ask Gemini to propose a structured execution plan (tool calls, sequence, parameters).
5. **ACT** — validate the plan through the Tool Guard, then execute approved steps.
6. **OBSERVE** — capture the result of every action (success, failure, partial).
7. **DIAGNOSE** — if something went wrong, identify root cause and classify the failure.
8. **RECOVER** — apply retry strategies, escalate, or fail gracefully.
9. **LEARN FROM EXECUTION DATA** — feed outcomes back into analytics for pattern detection.
10. **OPTIMIZE** — analyse accumulated KPIs, detect bottlenecks, and draft improvement proposals.
11. **RECOMMEND** — produce optimization recommendations that require human approval before taking effect.

---

## Non-Negotiables

These eight rules govern every file in this repo. They are not guidelines — they are invariants. Violating any of them is a bug.

1. **Gemini NEVER executes anything directly.** It only proposes a structured function call or a structured JSON decision. Our own Python code validates authorization, validates parameters, and performs the actual execution.

2. **Every tool call passes through the Tool Guard (allow-list + RBAC + parameter validation) before it runs.** No exceptions, no "just this once for the demo."

3. **Every external action is idempotent:** build a key from `{process_id}-{task_id}-{action}`, check `execution_receipts` for a prior `SUCCESS`, and skip re-execution if found.

4. **The permission matrix is hard-coded, not learned or inferred:** Agent 2 may create/update tasks, send email/reminders, create PO drafts, request quotations, update the mock ERP, analyze processes, and generate optimization proposals. Agent 2 may never approve a purchase, approve or execute a payment, change the official process definition, bypass Agent 4, or modify security policy — if Gemini's output ever asks for one of these, the Tool Guard blocks it and logs a security event; it does not get "interpreted charitably."

5. **Optimization recommendations always start as `PENDING_APPROVAL`** and only a human (via Agent 4/the approval endpoint) can move them to `APPROVED`. Agent 2 never self-approves its own recommendation.

6. **Email recipients are allow-listed by role** (requester, assigned employee, manager, finance officer, procurement officer, authorized escalation recipient) — never an arbitrary address Gemini produces.

7. **Every decision — allowed or blocked — gets an audit log entry** with actor, action, allowed/blocked, and reason.

8. **Agents 1, 3, and 4 don't exist yet.** Anywhere real data from them would be needed, use the seeded synthetic data or the mock Agent 4 service (`mock_agent4/`) — and comment `# MOCK:` at the integration seam so it's obvious what to swap out later.

---

## Folder Structure

```
agent_2/
  app/
    __init__.py
    main.py                        # FastAPI application entry point
    config.py                      # Pydantic-settings configuration
    agent/                         # Core agent logic (cognitive cycle)
      __init__.py
    llm/                           # Gemini LLM client and prompt management
      __init__.py
    execution/                     # Task execution engine
      __init__.py
    tools/                         # Tool implementations and Tool Guard
      __init__.py
    optimization/                  # Process optimization and recommendations
      __init__.py
    analytics/                     # KPI analytics, process mining
      __init__.py
    communication/                 # Email, notifications
      __init__.py
    security/                      # RBAC, permission matrix, audit logging
      __init__.py
    database/                      # SQLAlchemy models and DB utilities
      __init__.py
      models.py                    # 15 ORM models
  tests/
    __init__.py
  data/
    synthetic_cases/               # Seeded test data (Prompt 3)
  mock_agent4/                     # Mock Agent 4 service
    __init__.py
  alembic/                         # Database migrations
    env.py
    script.py.mako
    versions/
  scripts/
    init_pgvector.sql              # SQL init script for pgvector
  alembic.ini
  requirements.txt
  .env.example
  .gitignore
  README.md
  CLAUDE.md                        # ← You are here
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.12+ |
| Web framework | FastAPI |
| Validation | Pydantic v2 |
| ORM | SQLAlchemy 2.0 (async, asyncpg driver) |
| Migrations | Alembic |
| Database | PostgreSQL (Supabase, pgvector extension enabled) + Redis |
| LLM | google-genai (Gemini) |
| Email templates | Jinja2 |
| Analytics | pandas, numpy, pm4py |
| Testing | pytest, pytest-asyncio |

---

> **Read this file before doing anything else in this repo, every session.**
