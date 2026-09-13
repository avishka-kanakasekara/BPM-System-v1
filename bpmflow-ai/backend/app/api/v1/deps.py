"""FastAPI dependencies for API v1.

Uses the existing get_db() session factory. Tests override these callables.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent4_orchestrator.advancement_engine import ProcessAdvancementEngine
from app.agents.agent4_orchestrator.advancement_repository import (
    AdvancementRepository,
    get_advancement_repository,
)
from app.agents.agent4_orchestrator.approval_repository import (
    ApprovalRepository,
    SqlAlchemyApprovalRepository,
)
from app.agents.agent4_orchestrator.approvals import ApprovalService
from app.agents.agent4_orchestrator.audit_repository import (
    AuditRepository,
    SqlAlchemyAuditRepository,
)
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
from app.core.security import get_current_user, require_roles, require_tenant
from app.schemas.auth import CurrentUser


def resolve_approver_id(current_user: CurrentUser):
    """Return the authenticated approver id from CurrentUser."""
    return current_user.id


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


async def get_audit_repository(
    db: AsyncSession = Depends(get_db),
) -> AuditRepository:
    return SqlAlchemyAuditRepository(db)


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


async def get_policy_repository():
    from app.policy_knowledge import get_default_policy_repository

    return get_default_policy_repository()


async def get_policy_ingestion_service(
    repository=Depends(get_policy_repository),
):
    from app.policy_knowledge import PolicyIngestionService

    return PolicyIngestionService(repository)


async def get_policy_retrieval_service(
    repository=Depends(get_policy_repository),
):
    from app.policy_knowledge import PolicyRetrievalService

    return PolicyRetrievalService(repository)


async def get_advancement_repository_dep() -> AdvancementRepository:
    return get_advancement_repository()


async def get_agent4_workflow(
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
    approval_service: ApprovalService = Depends(get_approval_service),
    exception_service: ExceptionService = Depends(get_exception_service),
    policy_retrieval=Depends(get_policy_retrieval_service),
) -> Agent4Workflow:
    from app.agents.agent4_orchestrator.message_repository import get_agent_message_repository

    message_repository = get_agent_message_repository()
    return Agent4Workflow(
        orchestrator=orchestrator,
        approval_service=approval_service,
        exception_service=exception_service,
        policy_retrieval=policy_retrieval,
        message_repository=message_repository,
    )


async def get_process_advancement_engine(
    workflow: Agent4Workflow = Depends(get_agent4_workflow),
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
    process_repository: ProcessRepository = Depends(get_process_repository),
    advancement_repository: AdvancementRepository = Depends(get_advancement_repository_dep),
) -> ProcessAdvancementEngine:
    return ProcessAdvancementEngine(
        workflow=workflow,
        orchestrator=orchestrator,
        process_repository=process_repository,
        advancement_repository=advancement_repository,
    )


__all__ = [
    "resolve_approver_id",
    "get_current_user",
    "require_roles",
    "require_tenant",
    "get_process_repository",
    "get_approval_repository",
    "get_exception_repository",
    "get_audit_repository",
    "get_orchestrator_service",
    "get_approval_service",
    "get_exception_service",
    "get_policy_repository",
    "get_policy_ingestion_service",
    "get_policy_retrieval_service",
    "get_agent4_workflow",
    "get_advancement_repository_dep",
    "get_process_advancement_engine",
]
