# Agent 4: Orchestrator, Coordination & Risk Analysis

from .approval_repository import (
    InMemoryApprovalRepository,
    ApprovalRepository,
    SqlAlchemyApprovalRepository,
)
from .approvals import ApprovalService
from .constants import (
    HIGH_VALUE_PURCHASE_THRESHOLD,
    LOW_CONFIDENCE_THRESHOLD,
    ApprovalStatus,
    RiskLevel,
    RiskRecommendation,
    RiskType,
    WorkflowStage,
)
from .exceptions import (
    AgentUnavailableError,
    ApprovalAlreadyDecidedError,
    ApprovalNotFoundError,
    CommunicationFailureError,
    DatabasePersistenceError,
    InvalidMessageError,
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
    ProcessStateTransition,
    RiskAssessment,
    RiskEvaluationContext,
    RiskFinding,
)
from .communication import AgentAdapter
from .communication_service import AgentCommunicationService
from .adapters import Agent1Adapter, Agent2Adapter, Agent3Adapter
from .service import OrchestratorService
from .state_machine import (
    ALLOWED_TRANSITIONS,
    InvalidTransitionError,
    StateMachine,
)

__all__ = [
    "WorkflowStage",
    "ApprovalStatus",
    "RiskLevel",
    "RiskType",
    "RiskRecommendation",
    "HIGH_VALUE_PURCHASE_THRESHOLD",
    "LOW_CONFIDENCE_THRESHOLD",
    "ProcessStateTransition",
    "RiskEvaluationContext",
    "RiskFinding",
    "RiskAssessment",
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
    "InvalidTransitionError",
    "StateMachine",
]
