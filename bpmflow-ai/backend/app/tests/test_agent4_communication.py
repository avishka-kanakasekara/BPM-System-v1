"""Tests for Agent 4 agent-to-agent communication (no HTTP, no workflow)."""

import inspect
from uuid import uuid4

import pytest

from app.schemas.agent_message import (
    AGENT_1,
    AGENT_2,
    AGENT_3,
    AGENT_4,
    AgentMessage,
    AgentMessageMetadata,
    AgentMessageType,
)
from app.agents.agent4_orchestrator.adapters import (
    Agent1Adapter,
    Agent2Adapter,
    Agent3Adapter,
)
from app.agents.agent4_orchestrator.communication import AgentAdapter
from app.agents.agent4_orchestrator.communication_service import AgentCommunicationService
from app.agents.agent4_orchestrator.exceptions import (
    AgentUnavailableError,
    CommunicationFailureError,
    UnsupportedAgentError,
)


def _request(**overrides) -> AgentMessage:
    metadata = {
        "correlation_id": uuid4(),
        "process_instance_id": uuid4(),
        "task_id": uuid4(),
        "sender": AGENT_4,
        "receiver": AGENT_3,
        "message_type": AgentMessageType.RESOURCE_ALLOCATION_REQUEST,
    }
    metadata.update(overrides)
    return AgentMessage(
        metadata=AgentMessageMetadata(**metadata),
        payload={"human_requirements": {"required_roles": ["approver"]}},
    )


class RecordingAgent3Handler:
    def __init__(self) -> None:
        self.received: AgentMessage | None = None

    async def __call__(self, message: AgentMessage) -> AgentMessage:
        self.received = message
        return AgentMessage(
            metadata=AgentMessageMetadata(
                correlation_id=message.metadata.correlation_id,
                process_instance_id=message.metadata.process_instance_id,
                task_id=message.metadata.task_id,
                sender=AGENT_3,
                receiver=AGENT_4,
                message_type=AgentMessageType.RESOURCE_ALLOCATION_RESPONSE,
            ),
            payload={"status": "PENDING_HUMAN_APPROVAL"},
        )


class FailingAdapter(AgentAdapter):
    async def send(self, message: AgentMessage) -> AgentMessage:
        raise RuntimeError("socket reset")


@pytest.mark.asyncio
class TestAgent3Routing:
    async def test_valid_message_is_routed_to_agent3(self) -> None:
        handler = RecordingAgent3Handler()
        service = AgentCommunicationService(
            adapters={AGENT_3: Agent3Adapter(handler=handler)}
        )
        request = _request()
        response = await service.send(request)

        assert handler.received is request
        assert response.metadata.sender == AGENT_3
        assert response.metadata.receiver == AGENT_4
        assert response.metadata.message_type is (
            AgentMessageType.RESOURCE_ALLOCATION_RESPONSE
        )

    async def test_agent3_adapter_receives_expected_message(self) -> None:
        adapter = Agent3Adapter(handler=RecordingAgent3Handler())
        request = _request()
        await adapter.send(request)
        assert adapter.last_message is request
        assert adapter.last_message.payload["human_requirements"]["required_roles"] == [
            "approver"
        ]

    async def test_correlation_id_is_preserved(self) -> None:
        correlation_id = uuid4()
        service = AgentCommunicationService(
            adapters={AGENT_3: Agent3Adapter(handler=RecordingAgent3Handler())}
        )
        response = await service.send(_request(correlation_id=correlation_id))
        assert response.metadata.correlation_id == correlation_id

    async def test_process_instance_id_is_preserved(self) -> None:
        process_id = uuid4()
        service = AgentCommunicationService(
            adapters={AGENT_3: Agent3Adapter(handler=RecordingAgent3Handler())}
        )
        response = await service.send(_request(process_instance_id=process_id))
        assert response.metadata.process_instance_id == process_id

    async def test_task_id_is_preserved(self) -> None:
        task_id = uuid4()
        service = AgentCommunicationService(
            adapters={AGENT_3: Agent3Adapter(handler=RecordingAgent3Handler())}
        )
        response = await service.send(_request(task_id=task_id))
        assert response.metadata.task_id == task_id

    async def test_response_gets_a_new_message_id(self) -> None:
        service = AgentCommunicationService(
            adapters={AGENT_3: Agent3Adapter(handler=RecordingAgent3Handler())}
        )
        request = _request()
        response = await service.send(request)
        assert response.metadata.message_id != request.metadata.message_id

    async def test_message_serialization_remains_valid(self) -> None:
        service = AgentCommunicationService(
            adapters={AGENT_3: Agent3Adapter(handler=RecordingAgent3Handler())}
        )
        response = await service.send(_request())
        restored = AgentMessage.model_validate_json(response.model_dump_json())
        assert restored.metadata.correlation_id == response.metadata.correlation_id
        assert restored.payload == response.payload


@pytest.mark.asyncio
class TestUnavailableAndUnsupported:
    async def test_unsupported_receiver_is_rejected(self) -> None:
        service = AgentCommunicationService()
        with pytest.raises(UnsupportedAgentError):
            await service.send(_request(receiver="agent9"))

    async def test_agent1_unavailable_is_handled_cleanly(self) -> None:
        service = AgentCommunicationService()
        with pytest.raises(AgentUnavailableError) as exc_info:
            await service.send(
                _request(
                    receiver=AGENT_1,
                    message_type=AgentMessageType.PROCESS_DISCOVERY_REQUEST,
                )
            )
        assert exc_info.value.agent_id == AGENT_1

    async def test_agent2_unavailable_is_handled_cleanly(self) -> None:
        """A broken Agent 2 pipeline returns an ERROR envelope, never fake success."""

        class BrokenAgent2:
            async def handle(self, message, session=None):
                raise RuntimeError("execution pipeline down")

        service = AgentCommunicationService(
            adapters={AGENT_2: Agent2Adapter(agent=BrokenAgent2())}
        )
        request = _request(
            receiver=AGENT_2,
            message_type=AgentMessageType.WORKFLOW_EXECUTION_REQUEST,
        ).model_copy(update={"status": "AUTHORIZED"})
        response = await service.send(request)
        assert response.metadata.message_type is AgentMessageType.ERROR
        assert response.payload.get("error") == "AGENT2_EXECUTION_FAILED"
        assert response.payload.get("receipt_status") == "FAILED"
    async def test_agent2_never_receives_non_authorized_work(self) -> None:
        """Agent 2 invariant: only status=AUTHORIZED messages reach execution."""

        class MustNotRunAgent2:
            async def handle(self, message, session=None):
                raise AssertionError("Agent 2 must not execute non-authorized work")

        service = AgentCommunicationService(
            adapters={AGENT_2: Agent2Adapter(agent=MustNotRunAgent2())}
        )
        response = await service.send(
            _request(
                receiver=AGENT_2,
                message_type=AgentMessageType.WORKFLOW_EXECUTION_REQUEST,
            )
        )
        assert response.metadata.message_type is AgentMessageType.ERROR
        assert response.payload["error"] == "NOT_AUTHORIZED"

    async def test_adapter_communication_failure_is_handled(self) -> None:
        service = AgentCommunicationService(adapters={AGENT_3: FailingAdapter()})
        with pytest.raises(CommunicationFailureError):
            await service.send(_request())


class TestNoBusinessLogicDuplication:
    def test_agent4_does_not_duplicate_agent3_allocation_logic(self) -> None:
        """Agent 4 delegates to Agent 3's real service; it never re-implements
        eligibility, ranking, or scoring itself."""
        import app.agents.agent4_orchestrator.adapters as adapters_mod
        import app.agents.agent4_orchestrator.communication_service as comm_mod

        adapter_src = inspect.getsource(adapters_mod)
        comm_src = inspect.getsource(comm_mod)
        # The communication router stays agnostic of any agent's internals.
        assert "from app.agents.agent3_resources" not in comm_src
        # Allocation business logic must not be duplicated inside Agent 4.
        assert "EligibilityEvaluator" not in adapter_src
        assert "HumanResourceRanker" not in adapter_src
        assert "SCORING_WEIGHTS" not in adapter_src
        # The adapter delegates to Agent 3's real application service instead.
        assert "PersistentResourceAllocationService" in adapter_src
        assert "handler" in adapter_src
        assert Agent1Adapter is not None
        assert Agent2Adapter is not None
