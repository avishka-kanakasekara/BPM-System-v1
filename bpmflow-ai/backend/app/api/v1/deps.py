"""FastAPI dependencies for API v1.

Uses the existing get_db() session factory. Tests override these callables.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent4_orchestrator.approval_repository import InMemoryApprovalRepository
from app.agents.agent4_orchestrator.approvals import ApprovalService
from app.agents.agent4_orchestrator.repository import (
    ProcessRepository,
    SqlAlchemyProcessRepository,
)
from app.agents.agent4_orchestrator.service import OrchestratorService
from app.agents.agent4_orchestrator.workflow import Agent4Workflow
from app.core.database import get_db


async def get_process_repository(
    db: AsyncSession = Depends(get_db),
) -> ProcessRepository:
    return SqlAlchemyProcessRepository(db)


async def get_orchestrator_service(
    repository: ProcessRepository = Depends(get_process_repository),
) -> OrchestratorService:
    return OrchestratorService(repository=repository)


async def get_agent4_workflow(
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
) -> Agent4Workflow:
    return Agent4Workflow(
        orchestrator=orchestrator,
        approval_service=ApprovalService(
            orchestrator,
            InMemoryApprovalRepository(),
        ),
    )
