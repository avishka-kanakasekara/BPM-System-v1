from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings

app = FastAPI(
    title="BPMFlow AI",
    description="Four-agent, human-supervised agentic AI platform for Business Process Management",
    version="0.1.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "http://localhost:3000"],  # Vite default ports
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "message": "BPMFlow AI API",
        "version": "0.1.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "database": "configured" if settings.DATABASE_URL else "not configured",
        "supabase": "configured" if settings.SUPABASE_URL else "not configured"
    }


# Include routers (will be added when implemented)
# from app.api.v1.router import api_router
# app.include_router(api_router, prefix="/api/v1")
