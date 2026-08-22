# BPMFlow AI

BPMFlow AI is a four-agent, human-supervised agentic AI platform for Business Process Management (BPM). The platform features specialized agents for Process Discovery & Document Intelligence, Workflow Execution with RPA & Process Optimization, Workforce & Resource Allocation, and Orchestrator, Coordination & Risk Analysis. The demonstration scenario covers the end-to-end procurement process from purchase request to completion.

## Tech Stack

- **Frontend**: React (TypeScript) + Vite + Tailwind CSS
- **Backend**: Python + FastAPI + Pydantic, SQLAlchemy (async) ORM
- **Database**: Supabase (managed Postgres + Auth + Storage), pgvector enabled
- **LLM**: Pluggable OpenAI or Gemini client
- **Package Managers**: npm (frontend), pip + venv (backend)

## Project Structure

```
bpmflow-ai/
├── README.md                          # Project documentation
├── .gitignore                         # Git ignore patterns
├── docs/                              # Design documentation and API contracts
│   ├── design-report.md
│   └── api-contracts/
│       └── agent-messages.md
├── supabase/                          # Database migrations and config
│   ├── config.toml
│   ├── migrations/
│   │   └── 0001_init.sql
│   └── seed.sql
├── backend/                           # Python FastAPI backend
│   ├── requirements.txt
│   ├── .env.example
│   ├── Dockerfile
│   └── app/
│       ├── __init__.py
│       ├── main.py
│       ├── core/                      # Core configuration and utilities
│       │   ├── __init__.py
│       │   ├── config.py
│       │   ├── security.py
│       │   ├── database.py
│       │   └── logging.py
│       ├── api/                       # API route handlers
│       │   ├── __init__.py
│       │   └── v1/
│       │       ├── __init__.py
│       │       ├── router.py
│       │       ├── routes_process.py
│       │       ├── routes_agent1.py
│       │       ├── routes_agent2.py
│       │       ├── routes_agent3.py
│       │       ├── routes_agent4.py
│       │       ├── routes_auth.py
│       │       └── routes_audit.py
│       ├── agents/                    # Four AI agent implementations
│       │   ├── __init__.py
│       │   ├── agent1_discovery/
│       │   │   ├── __init__.py
│       │   │   ├── service.py
│       │   │   ├── document_parser.py
│       │   │   ├── extractors.py
│       │   │   └── schemas.py
│       │   ├── agent2_execution/
│       │   │   ├── __init__.py
│       │   │   ├── service.py
│       │   │   ├── rpa_tools.py
│       │   │   ├── kpi_analytics.py
│       │   │   └── schemas.py
│       │   ├── agent3_resources/
│       │   │   ├── __init__.py
│       │   │   ├── service.py
│       │   │   ├── retrieval.py
│       │   │   └── schemas.py
│       │   └── agent4_orchestrator/
│       │       ├── __init__.py
│       │       ├── service.py
│       │       ├── state_machine.py
│       │       ├── risk_rules.py
│       │       └── schemas.py
│       ├── llm/                       # LLM client integration
│       │   ├── __init__.py
│       │   ├── client.py
│       │   ├── structured_output.py
│       │   └── prompts/
│       │       └── __init__.py
│       ├── ir/                        # Information retrieval (vector store)
│       │   ├── __init__.py
│       │   ├── embeddings.py
│       │   ├── vector_store.py
│       │   └── reranker.py
│       ├── models/                    # SQLAlchemy ORM models
│       │   ├── __init__.py
│       │   ├── process.py
│       │   ├── user.py
│       │   ├── resource.py
│       │   ├── task.py
│       │   ├── audit.py
│       │   └── exception.py
│       ├── schemas/                   # Pydantic schemas
│       │   ├── __init__.py
│       │   ├── agent_message.py
│       │   └── common.py
│       └── tests/                     # Backend tests
│           ├── __init__.py
│           ├── test_agent1.py
│           ├── test_agent2.py
│           ├── test_agent3.py
│           ├── test_agent4.py
│           └── test_state_machine.py
├── frontend/                          # React TypeScript frontend
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── postcss.config.js
│   ├── index.html
│   ├── .env.example
│   ├── public/
│   │   └── .gitkeep
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── routes/
│       │   └── index.tsx
│       ├── pages/                     # Page components
│       │   ├── RequesterView/index.tsx
│       │   ├── TaskView/index.tsx
│       │   ├── ApprovalView/index.tsx
│       │   ├── ExceptionView/index.tsx
│       │   └── AuditTraceView/index.tsx
│       ├── components/                # Reusable components
│       │   ├── common/.gitkeep
│       │   └── agents/.gitkeep
│       ├── features/                  # Feature modules
│       │   ├── process/.gitkeep
│       │   ├── resources/.gitkeep
│       │   ├── approvals/.gitkeep
│       │   └── exceptions/.gitkeep
│       ├── services/                  # API and Supabase clients
│       │   ├── apiClient.ts
│       │   └── supabaseClient.ts
│       ├── hooks/.gitkeep
│       ├── store/.gitkeep
│       ├── types/.gitkeep
│       ├── styles/
│       │   └── tailwind.css
│       └── utils/.gitkeep
└── .github/                           # GitHub CI/CD workflows
    └── workflows/
        ├── backend-ci.yml
        └── frontend-ci.yml
```

## Agent 1 - Setup

Agent 1 (Process Discovery & Document Intelligence) is intended to run from `backend/` on its own. Process, auth, and other-agent routers are not mounted yet.

1. Copy environment defaults and edit values as needed:

   ```bash
   cd bpmflow-ai/backend
   python -m venv venv
   venv\Scripts\activate          # Windows
   pip install -r requirements.txt
   copy .env.example .env         # Windows; use `cp` on macOS/Linux
   ```

2. Set `DATABASE_URL` to a reachable Postgres instance (or SQLite, e.g. `sqlite:///./bpmflow.db`, for local-only work). Add `ANTHROPIC_API_KEY` when you enable LLM extraction. `MAX_UPLOAD_MB` and `ALLOWED_FILE_TYPES` control document ingestion.

3. Start the API:

   ```bash
   uvicorn app.main:app --reload --port 8001
   ```

4. Check `GET http://localhost:8001/health`. Interactive docs: `http://localhost:8001/docs`.

Optional: `python -m spacy download en_core_web_sm` if you want spaCy NER instead of the rule-based extractor.

## Status

This is an empty scaffold. Implementation has not started yet. All files are empty except for `.gitignore` and this `README.md`.
