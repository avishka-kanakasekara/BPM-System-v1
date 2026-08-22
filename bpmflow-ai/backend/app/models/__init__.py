"""SQLAlchemy ORM models."""

from app.models.agent_message import AgentMessageRecord
from app.models.audit import AuditLog, IngestionAuditLog
from app.models.document import DiscoveredDocument
from app.models.process import Process, ProcessExceptionRow, ProcessTask

__all__ = [
    "AgentMessageRecord",
    "AuditLog",
    "IngestionAuditLog",
    "DiscoveredDocument",
    "Process",
    "ProcessExceptionRow",
    "ProcessTask",
]

try:
    from app.models.approval import ApprovalRequest
    from app.models.exception import ProcessException
    from app.models.user import User

    __all__ += ["ApprovalRequest", "ProcessException", "User"]
except ImportError:
    pass
