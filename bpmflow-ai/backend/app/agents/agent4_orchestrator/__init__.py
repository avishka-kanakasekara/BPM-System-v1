# Agent 4: Orchestrator, Coordination & Risk Analysis

from .adapters import Agent1Adapter, Agent2Adapter, Agent3Adapter
from .approval_repository import (
    ApprovalRepository,
    InMemoryApprovalRepository,
    SqlAlchemyApprovalRepository,
)
from .approvals import ApprovalService
from .communication import AgentAdapter
from .communication_service import AgentCommunicationService
from .constants import (
    HIGH_VALUE_PURCHASE_THRESHOLD,
    LOW_CONFIDENCE_THRESHOLD,
    ApprovalStatus,
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    RiskLevel,
    RiskRecommendation,
    RiskType,
    WorkflowStage,
)
from .exception_repository import (
    ExceptionRepository,
    InMemoryExceptionRepository,
    SqlAlchemyExceptionRepository,
)
from .exception_service import ExceptionService
from .exceptions import (
    AgentUnavailableError,
    ApprovalAlreadyDecidedError,
    ApprovalNotFoundError,
    BpmExceptionNotFoundError,
    CommunicationFailureError,
    CompletionGateError,
    CrossTenantExceptionError,
    DatabasePersistenceError,
    ExecutionEnrichmentError,
    InvalidExceptionStatusError,
    InvalidMessageError,
    InvalidRetryError,
    ProcessAlreadyExistsError,
    ProcessNotFoundError,
    UnsupportedAgentError,
)
from .repository import (
    AUDIT_ACTION_UPDATED,
    AUDIT_ENTITY_PROCESS,
    InMemoryProcessRepository,
    ProcessRepository,
    SqlAlchemyProcessRepository,
)
from .risk_rules import RiskAnalysisEngine
from .schemas import (
    ApprovalDecisionResult,
    ApprovalGateResult,
    ApprovalRequestRecord,
    ExceptionRecord,
    ProcessStateTransition,
    RiskAssessment,
    RiskEvaluationContext,
    RiskFinding,
    WorkflowResult,
)
from .service import OrchestratorService
from .state_machine import (
    ALLOWED_TRANSITIONS,
    TRANSITION_TABLE,
    InvalidTransitionError,
    SideEffect,
    StateMachine,
    TransitionContext,
    TransitionPreconditionError,
    TransitionSpec,
)
from .workflow import Agent4Workflow
from .workflow_plan import WorkflowPlanService, WorkflowPlanValidator

__all__ = [
    "WorkflowStage",
    "ApprovalStatus",
    "ExceptionStatus",
    "ExceptionSeverity",
    "ExceptionType",
    "ExceptionRecord",
    "ExceptionService",
    "ExceptionRepository",
    "InMemoryExceptionRepository",
    "SqlAlchemyExceptionRepository",
    "BpmExceptionNotFoundError",
    "InvalidExceptionStatusError",
    "InvalidRetryError",
    "RiskLevel",
    "RiskType",
    "RiskRecommendation",
    "HIGH_VALUE_PURCHASE_THRESHOLD",
    "LOW_CONFIDENCE_THRESHOLD",
    "ProcessStateTransition",
    "RiskEvaluationContext",
    "RiskFinding",
    "RiskAssessment",
    "WorkflowResult",
    "Agent4Workflow",
    "RiskAnalysisEngine",
    "ApprovalService",
    "ApprovalRepository",
    "InMemoryApprovalRepository",
    "SqlAlchemyApprovalRepository",
    "ApprovalRequestRecord",
    "ApprovalDecisionResult",
    "ApprovalGateResult",
    "ApprovalNotFoundError",
    "ApprovalAlreadyDecidedError",
    "AgentAdapter",
    "AgentCommunicationService",
    "Agent1Adapter",
    "Agent2Adapter",
    "Agent3Adapter",
    "ExecutionEnrichmentError",
    "UnsupportedAgentError",
    "AgentUnavailableError",
    "InvalidMessageError",
    "CommunicationFailureError",
    "OrchestratorService",
    "ProcessAlreadyExistsError",
    "ProcessNotFoundError",
    "DatabasePersistenceError",
    "ProcessRepository",
    "InMemoryProcessRepository",
    "SqlAlchemyProcessRepository",
    "AUDIT_ENTITY_PROCESS",
    "AUDIT_ACTION_UPDATED",
    "ALLOWED_TRANSITIONS",
    "TRANSITION_TABLE",
    "TransitionSpec",
    "TransitionContext",
    "TransitionPreconditionError",
    "SideEffect",
    "InvalidTransitionError",
    "StateMachine",
    "WorkflowPlanService",
    "WorkflowPlanValidator",
]
