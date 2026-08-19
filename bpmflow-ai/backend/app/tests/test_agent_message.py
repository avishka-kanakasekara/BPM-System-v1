"""Tests for the shared inter-agent message contract."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.agent_message import (
    AGENT_1,
    AGENT_3,
    AGENT_4,
    SCHEMA_VERSION,
    AgentMessage,
    AgentMessageMetadata,
    AgentMessageType,
)


def _valid_metadata(**overrides) -> dict:
    base = {
        "correlation_id": uuid4(),
        "process_instance_id": uuid4(),
        "sender": AGENT_4,
        "receiver": AGENT_3,
        "message_type": AgentMessageType.RESOURCE_ALLOCATION_REQUEST,
    }
    base.update(overrides)
    return base


class TestAgentMessageMetadata:
    def test_valid_metadata(self) -> None:
        metadata = AgentMessageMetadata(**_valid_metadata(task_id=uuid4(), tenant_id=uuid4()))
        assert metadata.message_id is not None
        assert metadata.schema_version == SCHEMA_VERSION
        assert metadata.sender == AGENT_4
        assert metadata.receiver == AGENT_3
        assert metadata.timestamp.tzinfo is not None

    def test_missing_required_metadata(self) -> None:
        with pytest.raises(ValidationError):
            AgentMessageMetadata(
                sender=AGENT_4,
                receiver=AGENT_3,
                message_type=AgentMessageType.NOTIFICATION,
            )

    def test_timezone_aware_timestamp_required(self) -> None:
        naive = datetime(2026, 1, 1, 12, 0, 0)
        with pytest.raises(ValidationError):
            AgentMessageMetadata(
                **_valid_metadata(timestamp=naive),
            )

    def test_timezone_aware_timestamp_accepted(self) -> None:
        aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        metadata = AgentMessageMetadata(**_valid_metadata(timestamp=aware))
        assert metadata.timestamp.tzinfo is not None


class TestAgentMessageTypes:
    def test_existing_agent3_message_types_are_accepted(self) -> None:
        request = AgentMessageMetadata(
            **_valid_metadata(message_type=AgentMessageType.RESOURCE_ALLOCATION_REQUEST)
        )
        response = AgentMessageMetadata(
            **_valid_metadata(
                sender=AGENT_3,
                receiver=AGENT_4,
                message_type=AgentMessageType.RESOURCE_ALLOCATION_RESPONSE,
            )
        )
        assert request.message_type is AgentMessageType.RESOURCE_ALLOCATION_REQUEST
        assert response.message_type is AgentMessageType.RESOURCE_ALLOCATION_RESPONSE

    def test_generic_message_types_are_accepted(self) -> None:
        types = [
            AgentMessageType.PROCESS_DISCOVERY_REQUEST,
            AgentMessageType.PROCESS_DISCOVERY_RESPONSE,
            AgentMessageType.WORKFLOW_EXECUTION_REQUEST,
            AgentMessageType.WORKFLOW_EXECUTION_RESPONSE,
            AgentMessageType.NOTIFICATION,
            AgentMessageType.ALERT,
            AgentMessageType.ERROR,
        ]
        for message_type in types:
            metadata = AgentMessageMetadata(
                **_valid_metadata(sender=AGENT_1, receiver=AGENT_4, message_type=message_type)
            )
            assert metadata.message_type is message_type


class TestGenericAgentMessage:
    def test_valid_generic_message(self) -> None:
        message = AgentMessage(
            metadata=AgentMessageMetadata(**_valid_metadata()),
            payload={"action": "allocate"},
        )
        assert message.payload["action"] == "allocate"

    def test_payload_can_contain_nested_json_data(self) -> None:
        payload = {
            "requirements": {
                "human": {"roles": ["approver"], "hours": 8},
                "budget": {"amount": "25000.00", "currency": "USD"},
            },
            "flags": [True, False],
        }
        message = AgentMessage(
            metadata=AgentMessageMetadata(**_valid_metadata()),
            payload=payload,
        )
        assert message.payload["requirements"]["human"]["roles"] == ["approver"]
        assert message.payload["flags"] == [True, False]

    def test_json_serialization(self) -> None:
        correlation_id = uuid4()
        process_id = uuid4()
        message = AgentMessage(
            metadata=AgentMessageMetadata(
                correlation_id=correlation_id,
                process_instance_id=process_id,
                sender=AGENT_4,
                receiver=AGENT_3,
                message_type=AgentMessageType.RESOURCE_ALLOCATION_REQUEST,
            ),
            payload={"nested": {"ok": True}},
        )
        data = message.model_dump(mode="json")
        assert isinstance(data["metadata"]["message_id"], str)
        assert data["metadata"]["correlation_id"] == str(correlation_id)
        assert data["metadata"]["process_instance_id"] == str(process_id)
        assert data["metadata"]["sender"] == AGENT_4
        assert data["payload"]["nested"]["ok"] is True
        restored = AgentMessage.model_validate_json(message.model_dump_json())
        assert restored.metadata.correlation_id == correlation_id


class TestAgent3Compatibility:
    def test_importing_shared_schema_does_not_break_agent3_schemas(self) -> None:
        from app.agents.agent3_resources.schemas import (
            AgentMessageMetadata as Agent3Metadata,
        )
        from app.agents.agent3_resources.constants import (
            AGENT_3_SENDER,
            AGENT_4_RECEIVER,
            MessageType,
        )

        assert AgentMessageMetadata is not Agent3Metadata
        agent3_meta = Agent3Metadata(
            correlation_id=uuid4(),
            process_instance_id=uuid4(),
            task_id=uuid4(),
            tenant_id=uuid4(),
            message_type=MessageType.RESOURCE_ALLOCATION_REQUEST,
        )
        assert agent3_meta.sender == AGENT_3_SENDER
        assert agent3_meta.receiver == AGENT_4_RECEIVER
        assert agent3_meta.message_type is MessageType.RESOURCE_ALLOCATION_REQUEST
        assert AgentMessageType.RESOURCE_ALLOCATION_REQUEST.value == (
            MessageType.RESOURCE_ALLOCATION_REQUEST.value
        )
