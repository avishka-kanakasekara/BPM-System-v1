"""Agent 4 domain errors."""

from uuid import UUID


class ProcessNotFoundError(KeyError):
    """Raised when a process_id is not tracked or does not exist in the database."""

    def __init__(self, process_id: UUID) -> None:
        self.process_id = process_id
        super().__init__(f"Unknown process: {process_id}")


class ProcessAlreadyExistsError(ValueError):
    """Raised when create_process is called for an existing process_id."""

    def __init__(self, process_id: UUID) -> None:
        self.process_id = process_id
        super().__init__(f"Process already exists: {process_id}")


class DatabasePersistenceError(RuntimeError):
    """Raised when a database read or write fails during orchestration."""


class ApprovalNotFoundError(KeyError):
    """Raised when an approval request id does not exist."""

    def __init__(self, approval_id: UUID) -> None:
        self.approval_id = approval_id
        super().__init__(f"Unknown approval request: {approval_id}")


class ApprovalAlreadyDecidedError(ValueError):
    """Raised when a non-pending approval is approved or rejected again."""

    def __init__(self, approval_id: UUID, status: str) -> None:
        self.approval_id = approval_id
        self.status = status
        super().__init__(
            f"Approval request {approval_id} is already {status} and cannot be decided again"
        )


class UnsupportedAgentError(ValueError):
    """Raised when sender or receiver is not a known BPMFlow agent."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        super().__init__(f"Unsupported agent: {agent_id}")


class AgentUnavailableError(RuntimeError):
    """Raised when a known agent has no live implementation yet."""

    def __init__(self, agent_id: str, reason: str | None = None) -> None:
        self.agent_id = agent_id
        detail = reason or "implementation is not available yet"
        super().__init__(f"Agent {agent_id} is unavailable: {detail}")


class InvalidMessageError(ValueError):
    """Raised when an outbound or inbound agent message is invalid."""


class CommunicationFailureError(RuntimeError):
    """Raised when adapter communication fails unexpectedly."""
