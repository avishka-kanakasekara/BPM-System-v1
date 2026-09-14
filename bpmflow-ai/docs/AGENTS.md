# Agent responsibilities

Source of truth: `backend/app/agents/` and API routers. This is a **human-supervised** system.

| Agent | Responsibility | Cannot do |
|-------|----------------|-----------|
| **Agent 1** | Ingest allowed documents, extract evidence, hybrid IR search, populate ProcessContext / discovery JSON | Execute tools, approve, or write `current_stage` |
| **Agent 2** | Execute **one** authorized `WorkflowStep` via an allow-listed tool; persist a receipt; report KPIs | Approve humans’ work; chain a full workflow; change process stage |
| **Agent 3** | Rank eligible employees/resources and budget against directory + SoD | Execute procurement tools; approve; change process stage |
| **Agent 4** | Orchestrate stages, plans, risk, completion gate, exceptions | Bypass human approval when the gate is required; invent MATCHED invoices |
| **Human** | Approve / reject; activate workflow plans (approver/admin); review TO-BE; resolve/retry/fail exceptions (approver/admin); admin seeds and tool registry | — |

## Agent 1

- Routes under `/api/v1/agent1/`
- Insufficient evidence → abstain / incomplete facts, not invented vendors
- Document text is untrusted input (no tool execution from parsed text)

## Agent 2

- Canonical execute path: `POST /api/v1/workflows/{plan_id}/steps/{step_id}/execute`
- Contract: one request → one step → one allow-listed tool → one receipt
- `__full_task_suite__` is forbidden
- Legacy `POST /api/v1/agent2/execute` remains a **single-tool** path behind Agent 4 stage authorization

## Agent 3

- `POST /api/v1/agent3/allocations`
- Uses company directory employees, not hardcoded “developer” identities
- Recommendations are advisory until a human acts

## Agent 4

- Sole writer of process `current_stage` via `StateMachine`
- Completion requires persisted PO, invoice, MATCHED result, and the completion gate
- Does not auto-activate TO-BE recommendations
