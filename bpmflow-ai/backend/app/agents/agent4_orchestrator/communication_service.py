"""Route shared AgentMessages to in-process agent adapters.

Does not change workflow stage, evaluate risk, or create approvals.
"""


from pydantic import ValidationError

from app.messaging.envelope import build_response_envelope
from app.schemas.agent_message import (
    AGENT_1,
    AGENT_2,
    AGENT_3,
    AGENT_4,
    AgentMessage,
)

from .adapters import Agent1Adapter, Agent2Adapter, Agent3Adapter
from .communication import AgentAdapter
from .exceptions import (
    AgentUnavailableError,
    CommunicationFailureError,
    InvalidMessageError,
    UnsupportedAgentError,
)
from .message_repository import AgentMessageRepository

KNOWN_AGENTS = frozenset({AGENT_1, AGENT_2, AGENT_3, AGENT_4})
ROUTABLE_RECEIVERS = frozenset({AGENT_1, AGENT_2, AGENT_3})


class AgentCommunicationService:
    """Validates and routes Agent 4 outbound messages."""

    def __init__(
        self,
        adapters: dict[str, AgentAdapter] | None = None,
        message_repository: AgentMessageRepository | None = None,
    ) -> None:
        self._adapters = adapters or {
            AGENT_1: Agent1Adapter(),
            AGENT_2: Agent2Adapter(),
            AGENT_3: Agent3Adapter(),
        }
        self._message_repository = message_repository

    async def send(self, message: AgentMessage) -> AgentMessage:
        """Send a message to the adapter for message.metadata.receiver."""
        self._validate_message(message)
        if self._message_repository is not None:
            await self._message_repository.persist_outbound(message)
        receiver = message.metadata.receiver
        adapter = self._adapters.get(receiver)
        if adapter is None:
            raise UnsupportedAgentError(receiver)

        try:
            response = await adapter.send(message)
        except (AgentUnavailableError, UnsupportedAgentError, InvalidMessageError):
            raise
        except Exception as exc:
            raise CommunicationFailureError(
                f"Communication with {receiver} failed"
            ) from exc

        finalized = build_response_envelope(message, response)
        if self._message_repository is not None:
            await self._message_repository.persist_inbound(message, finalized)
        return finalized

    def _validate_message(self, message: AgentMessage) -> None:
        if not isinstance(message, AgentMessage):
            raise InvalidMessageError("Expected a shared AgentMessage")
        try:
            AgentMessage.model_validate(message.model_dump())
        except ValidationError as exc:
            raise InvalidMessageError("Agent message failed validation") from exc

        sender = message.metadata.sender
        receiver = message.metadata.receiver
        if sender not in KNOWN_AGENTS:
            raise UnsupportedAgentError(sender)
        if receiver not in KNOWN_AGENTS:
            raise UnsupportedAgentError(receiver)
        if receiver not in ROUTABLE_RECEIVERS:
            raise UnsupportedAgentError(receiver)

