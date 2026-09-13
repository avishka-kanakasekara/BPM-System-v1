"""G6: durable inter-agent messaging audit trail."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.agent4_orchestrator import ApprovalService, OrchestratorService
from app.agents.agent4_orchestrator.approval_repository import InMemoryApprovalRepository
from app.agents.agent4_orchestrator.communication_service import AgentCommunicationService
from app.agents.agent4_orchestrator.message_repository import InMemoryAgentMessageRepository
from app.agents.agent4_orchestrator.workflow import Agent4Workflow as WorkflowClass
from app.schemas.agent_message import (
    AGENT_3,
    AGENT_4,
    AgentMessage,
    AgentMessageMetadata,
    AgentMessageType,
)

pytestmark = pytest.mark.asyncio


class RecordingAgent3:
    async def __call__(self, message: AgentMessage) -> AgentMessage:
        return AgentMessage(
            metadata=AgentMessageMetadata(
                correlation_id=message.metadata.correlation_id,
                process_instance_id=message.metadata.process_instance_id,
                sender=AGENT_3,
                receiver=AGENT_4,
                message_type=AgentMessageType.RESOURCE_ALLOCATION_RESPONSE,
            ),
            payload={"status": "OK"},
        )


class TestG6MessagePersistence:
    async def test_communication_service_persists_outbound_and_inbound(self) -> None:
        from app.agents.agent4_orchestrator.adapters import Agent3Adapter

        repo = InMemoryAgentMessageRepository()
        service = AgentCommunicationService(
            adapters={AGENT_3: Agent3Adapter(handler=RecordingAgent3())},
            message_repository=repo,
        )
        process_id = uuid4()
        request = AgentMessage(
            metadata=AgentMessageMetadata(
                correlation_id=uuid4(),
                process_instance_id=process_id,
                sender=AGENT_4,
                receiver=AGENT_3,
                message_type=AgentMessageType.RESOURCE_ALLOCATION_REQUEST,
            ),
            payload={"human_requirements": {}},
        )
        await service.send(request)
        rows = await repo.list_for_process(process_id)
        assert len(rows) == 2
        assert {row.direction for row in rows} == {"outbound", "inbound"}
        assert rows[0].correlation_id == rows[1].correlation_id

    async def test_workflow_send_to_agent_persists_messages(self) -> None:
        from app.agents.agent4_orchestrator.adapters import Agent3Adapter
        from app.agents.agent4_orchestrator.constants import WorkflowStage
        from app.agents.agent4_orchestrator.exception_repository import InMemoryExceptionRepository
        from app.agents.agent4_orchestrator.exception_service import ExceptionService

        repo = InMemoryAgentMessageRepository()
        orchestrator = OrchestratorService()
        workflow = WorkflowClass(
            orchestrator=orchestrator,
            approval_service=ApprovalService(orchestrator, InMemoryApprovalRepository()),
            exception_service=ExceptionService(orchestrator, InMemoryExceptionRepository()),
            communication=AgentCommunicationService(
                adapters={AGENT_3: Agent3Adapter(handler=RecordingAgent3())},
                message_repository=repo,
            ),
            message_repository=repo,
        )
        process_id = uuid4()
        await orchestrator.create_process(
            process_id, initial_stage=WorkflowStage.RESOURCE_PLANNING
        )
        result = await workflow.plan_resources(process_id, payload={"process_id": str(process_id)})
        assert result.success is True
        rows = await repo.list_for_process(process_id)
        assert len(rows) == 2
        assert rows[0].from_agent == AGENT_4
        assert rows[1].from_agent == AGENT_3
