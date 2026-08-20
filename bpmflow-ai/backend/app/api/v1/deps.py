"""FastAPI dependencies for API v1.

Uses the existing get_db() session factory. Tests override these callables.
"""

from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent4_orchestrator.approval_repository import (
    ApprovalRepository,
    SqlAlchemyApprovalRepository,
)
from app.agents.agent4_orchestrator.approvals import ApprovalService
from app.agents.agent4_orchestrator.exception_repository import (
    ExceptionRepository,
    SqlAlchemyExceptionRepository,
)
from app.agents.agent4_orchestrator.exception_service import ExceptionService
from app.agents.agent4_orchestrator.repository import (
    ProcessRepository,
    SqlAlchemyProcessRepository,
)
from app.agents.agent4_orchestrator.service import OrchestratorService
from app.agents.agent4_orchestrator.workflow import Agent4Workflow
from app.core.database import get_db

# Placeholder approver until authentication is implemented.
# Not persisted as a user row; only stored on approval_requests.approver_id.
UNAUTHENTICATED_APPROVER_ID = UUID("00000000-0000-4000-8000-000000000001")


async def get_process_repository(
    db: AsyncSession = Depends(get_db),
) -> ProcessRepository:
    return SqlAlchemyProcessRepository(db)


async def get_approval_repository(
    db: AsyncSession = Depends(get_db),
) -> ApprovalRepository:
    return SqlAlchemyApprovalRepository(db)


async def get_exception_repository(
    db: AsyncSession = Depends(get_db),
) -> ExceptionRepository:
    return SqlAlchemyExceptionRepository(db)


async def get_orchestrator_service(
    repository: ProcessRepository = Depends(get_process_repository),
) -> OrchestratorService:
    return OrchestratorService(repository=repository)


async def get_approval_service(
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
    repository: ApprovalRepository = Depends(get_approval_repository),
) -> ApprovalService:
    return ApprovalService(orchestrator=orchestrator, repository=repository)


async def get_exception_service(
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
    repository: ExceptionRepository = Depends(get_exception_repository),
) -> ExceptionService:
    return ExceptionService(orchestrator=orchestrator, repository=repository)


async def get_agent4_workflow(
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
    approval_service: ApprovalService = Depends(get_approval_service),
    exception_service: ExceptionService = Depends(get_exception_service),
) -> Agent4Workflow:
    return Agent4Workflow(
        orchestrator=orchestrator,
        approval_service=approval_service,
        exception_service=exception_service,
    )
