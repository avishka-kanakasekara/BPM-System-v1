"""Tests for Phase 8 shared modules."""

from uuid import uuid4

from app.core.audit_writer import bpm_audit_orm, bpm_audit_payload
from app.messaging.envelope import build_agent_message, build_response_envelope
from app.schemas.agent_message import AGENT_2, AGENT_4, AgentMessageType
from app.schemas.errors import ErrorResponse


def test_error_response_from_code():
    from app.schemas.errors import ErrorDetail

    err = ErrorResponse.from_code("TEST", "Something failed", process_id="p1")
    assert isinstance(err.detail, ErrorDetail)
    assert err.detail.code == "TEST"


def test_bpm_audit_payload_shape():
    pid = uuid4()
    payload = bpm_audit_payload(
        entity_type="process",
        entity_id=pid,
        action="STAGE_UPDATED",
        old_values={"current_stage": "DRAFT"},
        new_values={"current_stage": "DISCOVERING"},
    )
    assert payload["entity_id"] == str(pid)
    assert payload["action"] == "STAGE_UPDATED"


def test_build_agent_message_and_response():
    process_id = uuid4()
    correlation_id = uuid4()
    request = build_agent_message(
        sender=AGENT_4,
        receiver=AGENT_2,
        message_type=AgentMessageType.WORKFLOW_EXECUTION_REQUEST,
        process_instance_id=process_id,
        correlation_id=correlation_id,
        payload={"task_id": "t1"},
        status="AUTHORIZED",
    )
    reply = build_agent_message(
        sender=AGENT_2,
        receiver=AGENT_4,
        message_type=AgentMessageType.WORKFLOW_EXECUTION_RESPONSE,
        process_instance_id=process_id,
        correlation_id=correlation_id,
        payload={"ok": True},
        status="EXECUTION_RESULT",
    )
    finalized = build_response_envelope(request, reply)
    assert finalized.metadata.sender == AGENT_2
    assert finalized.metadata.receiver == AGENT_4
    assert finalized.metadata.correlation_id == correlation_id


def test_bpm_audit_orm_entity_id():
    pid = uuid4()
    row = bpm_audit_orm(entity_type="process", entity_id=pid, action="CREATED")
    assert row.entity_id == pid
