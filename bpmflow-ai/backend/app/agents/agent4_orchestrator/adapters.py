"""In-process agent adapters used by Agent 4 communication.

Real integrations (no stubs):
- Agent1Adapter returns the persisted discovery result for the process.
  Discovery itself runs through Agent 1's upload endpoint; this adapter never
  invents discovery data — a missing discovery is an honest ERROR envelope.
- Agent2Adapter invokes Agent 2's cognitive execution pipeline in-process.
  It forwards only messages Agent 4 marked status="AUTHORIZED"; Agent 2's own
  Tool Guard still authorizes every individual tool call.
- Agent3Adapter maps the shared AgentMessage to Agent 3's strict local
  AllocationRequest, calls the existing allocation service, and maps the
  AllocationRecommendation back. It does not rank, score, or approve.

Every adapter raises AgentUnavailableError when its downstream dependency is
genuinely unreachable. None of them fabricate success responses.
"""

from typing import Awaitable, Callable, Optional
from uuid import uuid4

from pydantic import ValidationError

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


def _reply_metadata(
    request: AgentMessage,
    sender: str,
    message_type: AgentMessageType,
) -> AgentMessageMetadata:
    return AgentMessageMetadata(
        message_id=uuid4(),
        correlation_id=request.metadata.correlation_id,
        process_instance_id=request.metadata.process_instance_id,
        task_id=request.metadata.task_id,
        tenant_id=request.metadata.tenant_id,
        sender=sender,
        receiver=request.metadata.sender or AGENT_4,
        message_type=message_type,
        timestamp=utc_now(),
    )


def _error_reply(request: AgentMessage, sender: str, error: str, detail: str) -> AgentMessage:
    return AgentMessage(
        metadata=_reply_metadata(request, sender, AgentMessageType.ERROR),
        payload={"error": error, "detail": detail},
    )


async def _open_shared_session():
    """Return a live AsyncSession on the shared engine, or None."""
    from sqlalchemy import text

    from app.core.database import get_session_factory

    try:
        factory = get_session_factory()
    except ValueError:
        return None
    session = factory()
    try:
        await session.execute(text("SELECT 1"))
        return session
    except Exception:
        await session.close()
        return None


class Agent1Adapter(AgentAdapter):
    """Serves the real, persisted Agent 1 discovery output for a process.

    Agent 1's discovery pipeline runs when documents are uploaded via
    POST /api/v1/agent1/discover and persists a ProcessJSON on the process
    row. This adapter reads that result back for orchestration. It never
    invents discovery data and never writes approval fields.
    """

    async def send(self, message: AgentMessage) -> AgentMessage:
        from app.models.process import Process

        session = await _open_shared_session()
        if session is None:
            raise AgentUnavailableError(
                AGENT_1,
                "Shared database is unreachable; discovery results cannot be read",
            )
        try:
            row = await session.get(Process, message.metadata.process_instance_id)
        finally:
            await session.close()

        if row is None:
            return _error_reply(
                message,
                AGENT_1,
                "PROCESS_NOT_FOUND",
                "No process row exists for this process_instance_id",
            )
        if not row.process_json:
            return _error_reply(
                message,
                AGENT_1,
                "DISCOVERY_NOT_AVAILABLE",
                "No persisted discovery result for this process. Upload documents "
                "via POST /api/v1/agent1/discover first.",
            )

        return AgentMessage(
            metadata=_reply_metadata(
                message, AGENT_1, AgentMessageType.PROCESS_DISCOVERY_RESPONSE
            ),
            payload={
                "process_id": str(row.id),
                "name": row.name,
                "process_type": row.process_type,
                "discovery_status": row.discovery_status,
                "overall_confidence": row.overall_confidence,
                "process_json": row.process_json,
            },
            status=row.discovery_status,
            confidence=row.overall_confidence,
        )


class Agent2Adapter(AgentAdapter):
    """Invokes Agent 2's real cognitive execution pipeline in-process.

    Only messages that Agent 4 marked status="AUTHORIZED" are forwarded —
    Agent 2 executes pre-authorized work only, and its Tool Guard remains the
    final authority on every tool call.
    """

    def __init__(self, agent=None) -> None:
        self._agent = agent

    def _get_agent(self):
        if self._agent is None:
            from app.agents.agent2_execution.agent.agent import Agent2

            self._agent = Agent2()
        return self._agent

    async def send(self, message: AgentMessage) -> AgentMessage:
        from app.agents.agent2_execution.llm.schemas import (
            AgentMessage as Agent2WireMessage,
        )

        if message.status != "AUTHORIZED":
            return _error_reply(
                message,
                AGENT_2,
                "NOT_AUTHORIZED",
                "Agent 2 executes only pre-authorized work. Agent 4 must send "
                'status="AUTHORIZED" after the approval gate.',
            )

        payload = dict(message.payload)
        if message.metadata.task_id is not None:
            payload.setdefault("task_id", str(message.metadata.task_id))

        local_message = Agent2WireMessage(
            message_id=str(message.metadata.message_id),
            process_id=str(message.metadata.process_instance_id),
            trace_id=str(message.metadata.correlation_id),
            sender="agent_4",
            receiver="agent_2",
            task_type=str(payload.get("task_type") or "EXECUTE_TASK"),
            payload=payload,
            evidence_refs=list(message.evidence_refs),
            confidence=message.confidence if message.confidence is not None else 1.0,
            status="AUTHORIZED",
        )

        session = await _open_shared_session()
        try:
            response = await self._get_agent().handle(local_message, session=session)
        except Exception as exc:
            raise AgentUnavailableError(
                AGENT_2, f"Agent 2 execution pipeline failed: {exc}"
            ) from exc
        finally:
            if session is not None:
                await session.close()

        return AgentMessage(
            metadata=_reply_metadata(
                message, AGENT_2, AgentMessageType.WORKFLOW_EXECUTION_RESPONSE
            ),
            payload=dict(response.payload),
            status=response.status,
            confidence=response.confidence,
            evidence_refs=list(response.evidence_refs),
        )


async def _default_agent3_handler(message: AgentMessage) -> AgentMessage:
    """Map the shared envelope to Agent 3's local contract and back.

    Agent 3's local metadata requires task_id and tenant_id; a message
    without them is rejected with a validation ERROR envelope, never guessed.
    """
    from app.agents.agent3_resources.api_dependencies import (
        get_allocation_service,
        get_persistence_service,
    )
    from app.agents.agent3_resources.application_service import (
        PersistentResourceAllocationService,
    )
    from app.agents.agent3_resources.constants import (
        AGENT_4_RECEIVER,
        MessageType as Agent3MessageType,
    )
    from app.agents.agent3_resources.schemas import (
        AgentMessageMetadata as Agent3Metadata,
        AllocationRequest,
    )

    md = message.metadata
    if md.task_id is None or md.tenant_id is None:
        return _error_reply(
            message,
            AGENT_3,
            "AGENT3_VALIDATION_FAILED",
            "Agent 3 requires task_id and tenant_id in the message metadata",
        )

    try:
        local_metadata = Agent3Metadata(
            message_id=md.message_id,
            correlation_id=md.correlation_id,
            process_instance_id=md.process_instance_id,
            task_id=md.task_id,
            tenant_id=md.tenant_id,
            sender=AGENT_4_RECEIVER,
            receiver="agent3",
            message_type=Agent3MessageType.RESOURCE_ALLOCATION_REQUEST,
        )
        request = AllocationRequest(
            metadata=local_metadata,
            human_requirements=message.payload.get("human_requirements"),
            budget_requirements=message.payload.get("budget_requirements"),
        )
    except ValidationError as exc:
        return _error_reply(
            message,
            AGENT_3,
            "AGENT3_VALIDATION_FAILED",
            f"Allocation request failed Agent 3 validation: {exc}",
        )

    allocation_service = await get_allocation_service()
    persistence = await get_persistence_service()
    service = PersistentResourceAllocationService(allocation_service, persistence)

    try:
        result = await service.process_and_persist(request)
    except Exception as exc:
        raise AgentUnavailableError(
            AGENT_3, f"Agent 3 allocation/persistence failed: {exc}"
        ) from exc

    return AgentMessage(
        metadata=_reply_metadata(
            message, AGENT_3, AgentMessageType.RESOURCE_ALLOCATION_RESPONSE
        ),
        payload=result.model_dump(mode="json"),
        status=result.recommendation_status,
    )


class Agent3Adapter(AgentAdapter):
    """Boundary for Agent 3 resource allocation.

    Does not rank resources, check eligibility, or validate budgets — the
    default handler delegates to Agent 3's existing allocation service.
    A custom handler can still be injected for tests.
    """

    def __init__(self, handler: Optional[Agent3Handler] = None) -> None:
        self._handler = handler or _default_agent3_handler
        self.last_message: AgentMessage | None = None

    async def send(self, message: AgentMessage) -> AgentMessage:
        self.last_message = message
        return await self._handler(message)
