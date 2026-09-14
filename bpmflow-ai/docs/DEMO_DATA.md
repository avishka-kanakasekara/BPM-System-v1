# Demo data (fictional)

All of the following is **synthetic** for tests and university demonstration. It is not a real organization.

## Tenants (do not mix them up)

| ID | Used for |
|----|----------|
| `00000000-0000-0000-0000-00000000d001` | BPMFlow Demo Company directory, procurement, Phase 8–12 tests |
| `00000000-0000-0000-0000-000000000001` | Agent 3 synthetic allocation seed (`DEMO_TENANT_ID` / `seed_demo_tenant`) |

## How seeds are invoked

| Seed | How | Production |
|------|-----|------------|
| Company directory | `POST /api/v1/company/seed-demo` (admin) or `python -m app.scripts.seed_company_directory` | Refused when `ENV=production` and not DEBUG |
| Vendors | `POST /api/v1/vendors/seed-demo` (admin) or `seed_bpmflow_demo_procurement()` in tests | Same refusal |
| Agent 3 synthetic humans | `python -m app.scripts.seed_demo_tenant` (SQL upsert) | Manual only |
| Tool Registry | Test/startup seed helpers; register is admin API | No auto-seed on API boot |

Nothing above runs automatically in `lifespan` for production.

Repeated vendor/company seed **does not create duplicate vendor IDs**; it skips existing rows. Invoice demo helper `seed_bpmflow_demo_invoices` skips if invoices already exist for the demo process id.

## Departments (Demo Company)

Management, Finance, Procurement, IT, HR, Operations.

## Example employees (names are fictional)

| Number | Name | Role |
|--------|------|------|
| EMP-001 | Amina Perera | Senior Manager |
| EMP-010 | Nimal Fernando | Finance Manager |
| EMP-011 | Ishara Jayawardena | Finance Officer |
| EMP-020 | Ruwan Silva | Procurement Manager |
| EMP-021 | Dilani Karunaratne | Procurement Officer |
| … | (see `company_directory/seed.py`) | IT/HR/Ops/requester/inactive |

Emails: `*@bpmflow-demo.example.com`.

## Vendors (fictional)

| Code | Legal name |
|------|------------|
| vendor-it-01 | BPM Supplies Ltd |
| VENDOR-002 | TechSource Lanka |
| VENDOR-003 | Office Systems Lanka |
| VENDOR-001 | BPM Supplies Ltd alias |

Demo invoices/POs used in tests (for example `INV-DEMO-MATCHED`, `INV-PR-2026-0098`) are created by tests or `seed_bpmflow_demo_invoices`, not by production startup.

Quotations and POs for live demos are created **during the workflow**, not as a global master list of “always-on” POs.
