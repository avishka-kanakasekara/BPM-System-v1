# Testing

From `bpmflow-ai/backend` with the project venv:

```bash
python -m pytest app/tests
```

**Verified Phase 12 baseline:** 1195 passed, 38 skipped, 0 failed. Treat this as a snapshot; legitimate new tests may change the count.

**Phase 13 regression (this documentation phase):** 1196 passed, 38 skipped, 0 failed (adds `GET /health/demo` coverage).

## Slices

| Area | Command |
|------|---------|
| Full backend | `python -m pytest app/tests` |
| Agent 1 | `python -m pytest app/tests/test_agent1.py app/tests/test_agent1_pipeline.py app/tests/test_phase9_document_intelligence.py` |
| Agent 2 | `python -m pytest app/tests/agent2_execution app/tests/test_workflow_step_execution.py` |
| Agent 3 | `python -m pytest app/tests/test_agent3.py app/tests/test_agent3_g3.py app/tests/test_resource_service.py app/tests/test_agent3_api_contract.py` |
| Agent 4 | `python -m pytest app/tests/test_agent4_workflow.py app/tests/test_agent4_state_machine.py app/tests/test_agent4_g5.py` |
| Procurement / invoices | `python -m pytest app/tests/test_phase8b_procurement.py app/tests/test_phase8c_invoice_matching.py` |
| Exceptions / completion | `python -m pytest app/tests/test_phase8d_completion.py` |
| Monitoring / TO-BE | `python -m pytest app/tests/test_phase10_monitoring.py` |
| Security / RLS / Phase 12 | `python -m pytest app/tests/test_phase12_security.py app/tests/test_security.py app/tests/test_g10_production.py` |
| E2E procurement | `python -m pytest app/tests/test_phase11_e2e.py` |
| Integration (needs DB env) | `python -m pytest app/tests/integration` — many skip without `AGENT3_TEST_DATABASE_URL` |

Live Gemini tests may skip or fail on quota; they are not the Phase 12 baseline.

## Frontend

```bash
cd bpmflow-ai/frontend
npm test
npm run build
```

## Optional smoke script

`python -m app.scripts.e2e_smoke` — older golden-path helper. Prefer pytest Phase 11/12 for current procurement guarantees.
