"""SQLAlchemy ORM models."""

from app.models.agent_message import AgentMessageRecord
from app.models.audit import AuditLog, IngestionAuditLog
from app.models.document import DiscoveredDocument, DocumentChunk
from app.models.process import Process, ProcessExceptionRow, ProcessTask
from app.models.workflow import WorkflowPlan, WorkflowStep, WorkflowStepDependency
from app.models.tool_registry import ToolRegistryEntry
from app.models.tobe_recommendation import TobeRecommendation

__all__ = [
    "AgentMessageRecord",
    "AuditLog",
    "IngestionAuditLog",
    "DiscoveredDocument",
    "DocumentChunk",
    "Process",
    "ProcessExceptionRow",
    "ProcessTask",
    "WorkflowPlan",
    "WorkflowStep",
    "WorkflowStepDependency",
    "ToolRegistryEntry",
    "TobeRecommendation",
]

try:
    from app.models.approval import ApprovalRequest
    from app.models.exception import ProcessException
    from app.models.user import User

    __all__ += ["ApprovalRequest", "ProcessException", "User"]
except ImportError:
    pass
