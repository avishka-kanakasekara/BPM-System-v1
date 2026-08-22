# Agent 2 (standalone copy) — superseded

Agent 2 now lives in the FastAPI monolith at
`bpmflow-ai/backend/app/agents/agent2_execution`.

Do not start this directory as its own server. The `mock_agent4/` stand-in
has been removed; Agent 4 is the real in-process orchestrator.

Configure the unified `bpmflow-ai/backend/.env` (see `.env.example` there).
The Alembic history and `demo.py` in this folder are kept only as a
pre-integration reference.
