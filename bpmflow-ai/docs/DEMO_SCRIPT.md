# Procurement Demo — Click Path

**Duration:** ~5 minutes · **Prereqs:** backend on `:8000`, frontend on `:5173`, demo tenant seeded, sign in as requester + approver accounts.

Sample files: `sample-documents/procurement_event_log.csv`, `procurement_purchase_request.docx`.

## 1. Sign in (requester)

1. Open `http://localhost:5173`
2. Register or sign in as a **requester** (dev: any email via Supabase or `/api/v1/auth/register`)
3. **Expected:** Dashboard loads; navigation shows Discover, Processes

## 2. Discover process (Agent 1 — G2)

1. Go to **Discover**
2. Click **Create process** → name `Demo Procurement`, type `procurement`
3. Upload **CSV + DOCX** from `sample-documents/`
4. Submit discovery
5. **Expected:**
   - Success toast / status `NEEDS_CLARIFICATION` or `COMPLETE`
   - Activity list ≥ 5 steps (Submit PR → … → Pay Invoice)
   - Purchase amount ~4565 USD extracted from DOCX (visible in process detail risk section)

## 3. Open process cockpit

1. Navigate to **Processes** → open the new process
2. **Expected:**
   - Stage: `DRAFT` or `DISCOVERING`
   - Workflow timeline from discovery
   - Risk facts panel shows amount, vendor, evidence

## 4. Advance workflow (Agents 3 + 4 — G3, G5)

1. Click **Advance process** (or stage action equivalent)
2. **Expected:**
   - Stage moves through `RESOURCE_PLANNING` → `RISK_REVIEW`
   - For amount > policy threshold: lands on **`AWAITING_HUMAN_APPROVAL`**
   - Autonomous actions list shows `RESOURCE_PLANNING`, `RISK_REVIEW`
   - Agent 3 ranked candidates (when tenant configured)

## 5. Human approval (G5)

1. Sign out → sign in as **approver**
2. Open **Approvals** → select pending request for this process
3. Review risk level + reason
4. Click **Approve**
5. **Expected:**
   - Approval status `APPROVED`
   - Process advances toward execution (may complete automatically if low risk path)

## 6. Execution (Agent 2 — G4)

1. Return to process detail (as requester or approver)
2. **Expected:**
   - Stage `WORKFLOW_EXECUTION` then `INVOICE_MATCHING` on success
   - Receipt visible under Agent 2 / process metadata (PO draft)
   - If Gemini offline: receipt still succeeds with deterministic tool path

## 7. Invoice matching → COMPLETED (G7)

1. On process detail at `INVOICE_MATCHING`, open invoice form
2. Enter invoice number, amount matching PO, PO reference
3. Submit **Complete invoice matching**
4. **Expected:** Stage **`COMPLETED`**; success message; audit entries in timeline

## 8. Audit trail (G6)

1. Open **Audit** page
2. Filter by process id (or browse recent)
3. **Expected:** Stage transition rows; inter-agent messages queryable in DB (`agent_messages` ≥ 2 for process)

## API-only equivalent

```bash
GEMINI_OFFLINE=true MOCK_LLM=true python -m app.scripts.e2e_smoke
# 8/8 PASS — prints process_id, receipt_id, timings
```

## Troubleshooting during demo

| UI symptom | Check |
|------------|-------|
| "Process Stopped" at execution | Server logs; set `GEMINI_OFFLINE=true` |
| Approve button errors | Process missing discovery metadata — re-upload DOCX |
| Empty Agent 3 candidates | Run `python -m app.scripts.seed_demo_tenant` |
| Advance does nothing | Browser network tab: `/advance` response; see RUNBOOK |
