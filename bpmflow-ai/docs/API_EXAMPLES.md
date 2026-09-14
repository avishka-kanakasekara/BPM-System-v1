# API examples (fictional)

Replace `{token}` with a real JWT locally. Never paste production tokens into docs or tickets.

Base: `http://127.0.0.1:8000`

## Agent 1 discovery

```http
POST /api/v1/agent1/discover
Authorization: Bearer {token}
Content-Type: multipart/form-data

files: (PDF/DOCX/CSV)
```

Typical informational response fields: `process_id`, discovery payload, **no** `current_stage` mutation by Agent 1.

## Workflow plan

```http
POST /api/v1/processes/{process_id}/workflow/plan
Authorization: Bearer {token}
```

Then:

```http
POST /api/v1/workflows/{workflow_plan_id}/validate
Authorization: Bearer {token}
```

## Activate (approver or admin)

```http
POST /api/v1/workflows/{workflow_plan_id}/activate
Authorization: Bearer {token}
```

Example body of a successful plan: `"status": "ACTIVE"`.

## Agent 2 one-step execution

```http
POST /api/v1/workflows/{workflow_plan_id}/steps/{workflow_step_id}/execute
Authorization: Bearer {token}
Content-Type: application/json

{
  "process_id": "00000000-0000-0000-0000-00000000d010",
  "idempotency_key": "demo-po-once"
}
```

Client `authorization_state` is ignored. The server authorizes from plan status + process stage + step type.

Forbidden:

```http
POST /api/v1/agent2/execute
{
  "process_id": "...",
  "task_id": "...",
  "tool_name": "__full_task_suite__"
}
```

→ `403` `FULL_WORKFLOW_EXECUTION_FORBIDDEN`.

## Invoice matching (Agent 4)

```http
POST /api/v1/processes/{process_id}/complete-invoice-matching
Authorization: Bearer {token}
Content-Type: application/json

{
  "invoice_number": "INV-PR-2026-0098"
}
```

Matching uses **persisted** PO and invoice rows. `expected_amount` in a body cannot force MATCHED.

## Monitoring

```http
GET /api/v1/processes/{process_id}/timeline
GET /api/v1/processes/{process_id}/kpis
GET /api/v1/processes/{process_id}/monitoring
Authorization: Bearer {token}
```

## TO-BE recommendation

```http
POST /api/v1/processes/{process_id}/recommendations/generate
Authorization: Bearer {token}
```

```http
POST /api/v1/recommendations/{recommendation_id}/review
Authorization: Bearer {token}
Content-Type: application/json

{
  "decision": "ACCEPTED",
  "notes": "Fictional reviewer note"
}
```

Review does **not** activate a WorkflowPlan.
