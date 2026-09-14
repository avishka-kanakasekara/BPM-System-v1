# Repair Changelog

> Historical defect register for Phases 1–10. Current handover docs: [README](../README.md), [ARCHITECTURE.md](ARCHITECTURE.md), [SECURITY.md](SECURITY.md).

Defect resolutions across Phases 1–10. Format: **ID** — root cause → fix.

## Phase 10 (2026-09-13)

| ID | Resolution |
|----|------------|
| D-018 | No golden path script → added `app/scripts/e2e_smoke.py` (G1–G8, exit code, timing table) |
| D-006 | Agent 4 messages not persisted → `RestAgentMessageRepository` wired in `get_agent4_workflow`; omit ephemeral `task_id` on REST insert to satisfy FK |
| D-001 (partial) | Advance 500 when `process_advancement_runs` missing → `ResilientAdvancementRepository` falls back to in-memory idempotency |
| D-009 (partial) | Discovery metadata not visible to Agent 4 on REST → `process_from_rest()` merges `process_json` + description JSON into `metadata_json` |
| D-015 | Stale README "empty scaffold" → rewritten `README.md` with verified setup |
| D-016 | Frontend tests broken → `npm install`; 236 Vitest pass |
| D-017 | Live Gemini in default pytest → exclude `test_gemini_live.py` in CI command |
| D-010 (partial) | Approval integration tests 422 → seed `DISCOVERY_META` in `_create_pending_approval` |

## Phase 9

| ID | Resolution |
|----|------------|
| D-005 | `/health` false green → `/health/deps` per-probe matrix; `test_g10_production.py` |
| G10 | Production guards → middleware stack, redaction, rate limits, shutdown drain, `assert_production_config()` |

## Phase 8

| ID | Resolution |
|----|------------|
| D-020 | Legacy `agent_2/` confusion → deleted approved tree |
| D-014 | Dead `messages.py` route → deleted |
| SF-* (partial) | Shared `audit_writer`, `errors`, `email`, `llm/retry`, `messaging/envelope` |
| — | ruff + scoped mypy green |

## Phase 7

| ID | Resolution |
|----|------------|
| G8 (partial) | Frontend build errors → ProcessDetailPage, API types, RBAC routes; 236 tests |
| D-016 | Corrupt node_modules → clean install |

## Still open (environment / deferred)

| ID | Status | Blocker |
|----|--------|---------|
| D-001 | PARTIAL | Postgres pooler DNS invalid; REST fallback works |
| D-002 | OPEN | Migration 0008 policy tables not on remote Supabase |
| D-003 | MITIGATED | Use `GEMINI_OFFLINE=true` for smoke; live quota still exhausted |
| D-004 | PARTIAL | Retry UX improved; transient LLM still stalls without offline mode |
| D-011 | OPEN | Legacy threshold when policy DB missing |
| D-012 | PARTIAL | Demo tenant seed works when migrations applied |
| D-019 | PARTIAL | Scheduler tables exist; integration test added in pytest |

## Verification snapshot (2026-09-13)

```
pytest: 914 passed, 14 skipped (excl. live Gemini)
npm run build: success
npm test: 236 passed
python -m app.scripts.e2e_smoke: 8/8 PASS
ruff check app: pass
mypy (scoped): pass
```
