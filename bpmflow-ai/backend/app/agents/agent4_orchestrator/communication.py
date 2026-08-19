"""Abstract in-process communication interface for Agent 4.

Transport-agnostic: adapters may later wrap HTTP, queues, or local services.
"""

from abc import ABC, abstractmethod

from app.schemas.agent_message import AgentMessage


class AgentAdapter(ABC):
    """Sends one AgentMessage and returns one AgentMessage."""

    @abstractmethod
    async def send(self, message: AgentMessage) -> AgentMessage:
        """Deliver message to a collaborator agent and return its response."""
