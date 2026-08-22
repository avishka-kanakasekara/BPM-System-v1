# Agent 2 — Intelligent Workflow Execution, RPA & Process Optimization

Part of the **BPMFlow AI** four-agent platform. Agent 2 is a bounded-autonomy LLM agent that receives authorized tasks from Agent 4, plans execution with Google Gemini, executes through approved tools, and produces evidence-based optimization recommendations.

See [CLAUDE.md](CLAUDE.md) for the full architecture, non-negotiable rules, and folder structure.

## Quick Start

```bash
# 1. Create virtual environment
python -m venv venv && source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — set DATABASE_URL, GEMINI_API_KEY, etc.

# 4. Run database migrations
alembic upgrade head

# 5. Start the server
uvicorn app.main:app --reload --port 8002
```

## Tech Stack

Python 3.12+ · FastAPI · SQLAlchemy 2.0 (async) · Alembic · PostgreSQL (Supabase / pgvector) · Redis · google-genai (Gemini) · Jinja2 · pandas · pm4py · pytest
