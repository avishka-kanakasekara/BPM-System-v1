# Procurement demo guide

Fictional scenarios used in tests: **PR-2026-0098** (happy path) and **PR-2026-0105** (blocked). Data is **not** real company information.

**Prereqs:** API on `:8000`, UI on `:5174`, JWT with tenant `00000000-0000-0000-0000-00000000d001` (BPMFlow Demo Company), directory + vendor seeds applied, at least one **requester** and one **approver**.

Sample files: `sample-documents/procurement_purchase_request.docx`, `procurement_event_log.csv`, `procurement_sop.docx`.

## Successful path — PR-2026-0098

1. **Upload** procurement documents on **Discover** (`POST /api/v1/agent1/discover`).
2. **Agent 1** extracts purchase facts into ProcessContext (amount, vendor name, evidence). Amounts come from documents, not hardcoded USD defaults.
3. Open **Processes → detail**. Evidence / process JSON is visible; stage is still owned by Agent 4 (`DRAFT` until start/advance).
4. **Plan:** `POST /api/v1/processes/{id}/workflow/plan` (or UI equivalent). Agent 4 builds WorkflowPlan + steps.
5. **Allocate:** `POST /api/v1/processes/{id}/plan-resources` — Agent 3 ranks **directory employees**, not fake “python developer” defaults.
6. High-value / policy hits open **AWAITING_HUMAN_APPROVAL**.
7. Sign in as **approver**. **Approvals → Approve**. Agent 4 moves to `WORKFLOW_EXECUTION`.
8. Approver/admin **activates** the plan (`POST /api/v1/workflows/{id}/activate`) after validation. Unresolved human steps cannot activate.
9. **Agent 2** executes the PO step only: `POST /api/v1/workflows/{plan}/steps/{step}/execute`.
10. A **real persisted purchase order** exists (`GET /api/v1/processes/{id}/purchase-order`).
11. Persist an **invoice** (admin `POST /api/v1/invoices` or demo tooling) matching PO lines.
12. Execute the **match-invoice** WorkflowStep (Agent 2) **or** Agent 4 `complete-invoice-matching` after the invoice exists.
13. Invoice status **MATCHED** on the stored row.
14. Agent 4 **completion gate** (PO, invoice, MATCHED, no blocking exception, required steps).
15. Process **COMPLETED**.
16. `GET /api/v1/processes/{id}/timeline` and `/kpis` / `/monitoring`.
17. `POST /api/v1/processes/{id}/recommendations/generate` — human must **review**; nothing auto-activates.

Automated regression of this path: `python -m pytest app/tests/test_phase11_e2e.py -q`

## Invalid path — PR-2026-0105

Expected when policy/budget/quotation/SoD rules fire:

- Process goes to **EXCEPTION** (or stays blocked before PO).
- **No unauthorized purchase order.**
- **Cannot become COMPLETED** through matching or execute shortcuts.

Covered in `test_phase11_e2e.py` (blocked / exception assertions).

## UI click path (evaluation)

1. Sign in requester → Discover → upload sample documents.
2. Processes → open the process → start / plan resources as the UI exposes.
3. Sign in approver → Approvals → approve.
4. Return to process detail → execute authorized step / invoice matching form.
5. Audit page for trail.

If the UI lacks a control (TO-BE review, one-step execute), use `/docs` — that is a **frontend limitation**, not a missing backend capability.

## Reproducibility

- Vendor and company seeds are **idempotent** (skip existing vendor ids / codes).
- `python -m app.scripts.seed_company_directory` **resets the in-memory directory** then reseeds; it does not truncate live Postgres employee tables. There is **no safe destructive “wipe all processes”** tool; create a new process for a clean demo.
