"""In-process agent adapters used by Agent 4 communication.

Agent 1 and Agent 2 are stubs: they do not invent business results.
Agent 3 does not duplicate allocation logic. Wire an optional handler that
maps the shared AgentMessage to Agent 3's local AllocationRequest, calls the
existing Agent 3 service, then maps AllocationRecommendation back.
"""

from typing import Awaitable, Callable, Optional
from uuid import uuid4

from app.schemas.agent_message import (
    AGENT_1,
    AGENT_2,
    AGENT_3,
    AGENT_4,
    AgentMessage,
    AgentMessageMetadata,
    AgentMessageType,
    utc_now,
)

from .communication import AgentAdapter
from .exceptions import AgentUnavailableError

Agent3Handler = Callable[[AgentMessage], Awaitable[AgentMessage]]


class Agent1Adapter(AgentAdapter):
    """Stub. Process discovery is not implemented."""

    async def send(self, message: AgentMessage) -> AgentMessage:
        raise AgentUnavailableError(
            AGENT_1,
            "Process discovery (Agent 1) is not implemented yet",
        )


class Agent2Adapter(AgentAdapter):
    """Stub. Workflow execution is not implemented."""

    async def send(self, message: AgentMessage) -> AgentMessage:
        raise AgentUnavailableError(
            AGENT_2,
            "Workflow execution (Agent 2) is not implemented yet",
        )


class Agent3Adapter(AgentAdapter):
    """Boundary for Agent 3 resource allocation.

    Does not rank resources, check eligibility, or validate budgets.
    If no handler is wired, returns a controlled ERROR envelope rather than
    a fake AllocationRecommendation.
    """

    def __init__(self, handler: Optional[Agent3Handler] = None) -> None:
        self._handler = handler
        self.last_message: AgentMessage | None = None

    async def send(self, message: AgentMessage) -> AgentMessage:
        self.last_message = message
        if self._handler is not None:
            return await self._handler(message)
        return AgentMessage(
            metadata=AgentMessageMetadata(
                message_id=uuid4(),
                correlation_id=message.metadata.correlation_id,
                process_instance_id=message.metadata.process_instance_id,
                task_id=message.metadata.task_id,
                tenant_id=message.metadata.tenant_id,
                sender=AGENT_3,
                receiver=message.metadata.sender or AGENT_4,
                message_type=AgentMessageType.ERROR,
                timestamp=utc_now(),
            ),
            payload={
                "error": "AGENT3_NOT_WIRED",
                "detail": (
                    "Wire Agent3Adapter(handler=...) to Agent 3's existing "
                    "resource allocation service. "
                    "Do not implement allocation logic in Agent 4."
                ),
            },
        )
