"""Durable persistence for inter-agent AgentMessage envelopes (G6)."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.core.supabase_rest import rest_insert, rest_select, supabase_rest_configured
from app.schemas.agent_message import AgentMessage


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class PersistedAgentMessage:
    id: UUID
    from_agent: str
    to_agent: str
    message_type: str
    content: dict[str, Any]
    process_id: UUID | None
    task_id: UUID | None
    status: str
    direction: str
    correlation_id: UUID | None = None
    created_at: datetime = field(default_factory=_utc_now)


class AgentMessageRepository(ABC):
    @abstractmethod
    async def persist_outbound(self, message: AgentMessage) -> PersistedAgentMessage:
        raise NotImplementedError

    @abstractmethod
    async def persist_inbound(
        self,
        request: AgentMessage,
        response: AgentMessage,
    ) -> PersistedAgentMessage:
        raise NotImplementedError

    @abstractmethod
    async def list_for_process(self, process_id: UUID) -> list[PersistedAgentMessage]:
        raise NotImplementedError


class InMemoryAgentMessageRepository(AgentMessageRepository):
    """Test / offline store for orchestration message audit trail."""

    def __init__(self) -> None:
        self.messages: list[PersistedAgentMessage] = []

    async def persist_outbound(self, message: AgentMessage) -> PersistedAgentMessage:
        row = PersistedAgentMessage(
            id=message.metadata.message_id,
            from_agent=message.metadata.sender,
            to_agent=message.metadata.receiver,
            message_type=message.metadata.message_type.value,
            content=message.model_dump(mode="json"),
            process_id=message.metadata.process_instance_id,
            task_id=message.metadata.task_id,
            status=message.status or "sent",
            direction="outbound",
            correlation_id=message.metadata.correlation_id,
        )
        self.messages.append(row)
        return row

    async def persist_inbound(
        self,
        request: AgentMessage,
        response: AgentMessage,
    ) -> PersistedAgentMessage:
        row = PersistedAgentMessage(
            id=response.metadata.message_id,
            from_agent=response.metadata.sender,
            to_agent=response.metadata.receiver,
            message_type=response.metadata.message_type.value,
            content=response.model_dump(mode="json"),
            process_id=response.metadata.process_instance_id,
            task_id=response.metadata.task_id,
            status=response.status or "received",
            direction="inbound",
            correlation_id=request.metadata.correlation_id,
        )
        self.messages.append(row)
        return row

    async def list_for_process(self, process_id: UUID) -> list[PersistedAgentMessage]:
        return [m for m in self.messages if m.process_id == process_id]


def _persist_outbound_rest(message: AgentMessage) -> PersistedAgentMessage:
    row = {
        "id": str(message.metadata.message_id),
        "from_agent": message.metadata.sender,
        "to_agent": message.metadata.receiver,
        "message_type": message.metadata.message_type.value,
        "content": message.model_dump(mode="json"),
        "process_id": str(message.metadata.process_instance_id),
        "status": message.status or "sent",
    }
    rest_insert("agent_messages", row)
    return PersistedAgentMessage(
        id=message.metadata.message_id,
        from_agent=message.metadata.sender,
        to_agent=message.metadata.receiver,
        message_type=message.metadata.message_type.value,
        content=message.model_dump(mode="json"),
        process_id=message.metadata.process_instance_id,
        task_id=message.metadata.task_id,
        status=message.status or "sent",
        direction="outbound",
        correlation_id=message.metadata.correlation_id,
    )


def _persist_inbound_rest(request: AgentMessage, response: AgentMessage) -> PersistedAgentMessage:
    row = {
        "id": str(response.metadata.message_id),
        "from_agent": response.metadata.sender,
        "to_agent": response.metadata.receiver,
        "message_type": response.metadata.message_type.value,
        "content": response.model_dump(mode="json"),
        "process_id": str(response.metadata.process_instance_id),
        "status": response.status or "received",
    }
    rest_insert("agent_messages", row)
    return PersistedAgentMessage(
        id=response.metadata.message_id,
        from_agent=response.metadata.sender,
        to_agent=response.metadata.receiver,
        message_type=response.metadata.message_type.value,
        content=response.model_dump(mode="json"),
        process_id=response.metadata.process_instance_id,
        task_id=response.metadata.task_id,
        status=response.status or "received",
        direction="inbound",
        correlation_id=request.metadata.correlation_id,
    )


def _list_for_process_rest(process_id: UUID) -> list[PersistedAgentMessage]:
    rows = rest_select(
        "agent_messages",
        {
            "process_id": f"eq.{process_id}",
            "select": "id,from_agent,to_agent,message_type,content,process_id,task_id,status,created_at",
            "order": "created_at.asc",
        },
    )
    persisted: list[PersistedAgentMessage] = []
    for row in rows:
        content = row.get("content") if isinstance(row.get("content"), dict) else {}
        correlation_raw = None
        if isinstance(content, dict):
            metadata = content.get("metadata")
            if isinstance(metadata, dict):
                correlation_raw = metadata.get("correlation_id")
        direction = "inbound" if row.get("from_agent") != "agent4" else "outbound"
        persisted.append(
            PersistedAgentMessage(
                id=UUID(str(row["id"])),
                from_agent=str(row.get("from_agent") or ""),
                to_agent=str(row.get("to_agent") or ""),
                message_type=str(row.get("message_type") or ""),
                content=content,
                process_id=UUID(str(row["process_id"])) if row.get("process_id") else None,
                task_id=UUID(str(row["task_id"])) if row.get("task_id") else None,
                status=str(row.get("status") or "sent"),
                direction=direction,
                correlation_id=UUID(str(correlation_raw)) if correlation_raw else None,
                created_at=datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00")),
            )
        )
    return persisted


class RestAgentMessageRepository(AgentMessageRepository):
    """Persist orchestrator envelopes via Supabase REST (service role)."""

    async def persist_outbound(self, message: AgentMessage) -> PersistedAgentMessage:
        return await asyncio.to_thread(_persist_outbound_rest, message)

    async def persist_inbound(
        self,
        request: AgentMessage,
        response: AgentMessage,
    ) -> PersistedAgentMessage:
        return await asyncio.to_thread(_persist_inbound_rest, request, response)

    async def list_for_process(self, process_id: UUID) -> list[PersistedAgentMessage]:
        return await asyncio.to_thread(_list_for_process_rest, process_id)


def get_agent_message_repository() -> AgentMessageRepository | None:
    if supabase_rest_configured():
        return RestAgentMessageRepository()
    return None
