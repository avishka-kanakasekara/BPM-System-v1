# Process state machine

Source of truth: `app/agents/agent4_orchestrator/constants.py` (`WorkflowStage`) and `state_machine.py` (`TRANSITION_TABLE`).

**Agent 4 owns every process-stage change.** Agent 1, 2, and 3 must not write `current_stage`.

## Stages (implemented)

| Stage | Meaning |
|-------|---------|
| `DRAFT` | Process row exists; discovery not started |
| `DISCOVERING` | Agent 1 discovery in progress / just started |
| `RESOURCE_PLANNING` | Agent 3 allocation |
| `RISK_REVIEW` | Deterministic risk / policy evaluation |
| `AWAITING_HUMAN_APPROVAL` | Human gate open |
| `WORKFLOW_EXECUTION` | Authorized Agent 2 steps may run |
| `INVOICE_MATCHING` | Persisted invoice vs PO |
| `COMPLETED` | Completion gate passed |
| `EXCEPTION` | Blocking exception recorded |

There is **no** implemented process stage named `CANCELLED` or `SUPERSEDED`. (Workflow **plans** have their own statuses such as ACTIVE / cancelled / superseded.)

## Allowed transitions

| From | To | Guard |
|------|----|--------|
| DRAFT | DISCOVERING | — |
| DISCOVERING | RESOURCE_PLANNING | — |
| RESOURCE_PLANNING | RISK_REVIEW | — |
| RISK_REVIEW | AWAITING_HUMAN_APPROVAL | Human approval required |
| RISK_REVIEW | WORKFLOW_EXECUTION | Human approval **not** required |
| AWAITING_HUMAN_APPROVAL | WORKFLOW_EXECUTION | Approval status APPROVED |
| AWAITING_HUMAN_APPROVAL | EXCEPTION | Approval REJECTED |
| WORKFLOW_EXECUTION | INVOICE_MATCHING | Agent 2 receipt SUCCESS |
| WORKFLOW_EXECUTION | EXCEPTION | Execution failure / block |
| INVOICE_MATCHING | COMPLETED | Invoice match MATCHED (+ completion gate in workflow) |
| INVOICE_MATCHING | EXCEPTION | Mismatch / insufficient evidence |
| EXCEPTION | DISCOVERING | Recovery authorized |
| EXCEPTION | COMPLETED | Exception resolved (still subject to completion rules in services) |

Illegal jumps (for example DRAFT → COMPLETED) raise `InvalidTransitionError`.

## Side effects (named, not LLM)

Recorded on the spec for audit/orchestration hooks: `START_DISCOVERY`, `OPEN_RESOURCE_PLANNING`, `OPEN_RISK_REVIEW`, `OPEN_HUMAN_APPROVAL_GATE`, `AUTHORIZE_EXECUTION`, `DISPATCH_AGENT2`, `OPEN_INVOICE_MATCHING`, `COMPLETE_PROCESS`, `RECORD_EXCEPTION`, `RETRY_FROM_DISCOVERY`, `CLOSE_EXCEPTION`.
