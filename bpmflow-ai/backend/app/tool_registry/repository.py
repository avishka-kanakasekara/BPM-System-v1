"""Tool Registry persistence: in-memory tests + SQLAlchemy production path."""

from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool_registry import ToolRegistryEntry

from .constants import ToolActionCode, ToolCategory
from .exceptions import DuplicateToolError, ToolNotFoundError
from .implementations import resolve_implementation
from .schemas import RegisterToolInput, ToolRegistryRecord


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ToolRegistryRepository(ABC):
    @abstractmethod
    async def insert(self, record: ToolRegistryRecord) -> ToolRegistryRecord: ...

    @abstractmethod
    async def get(self, tool_id: UUID, *, tenant_id: UUID) -> ToolRegistryRecord: ...

    @abstractmethod
    async def list_tools(self, *, tenant_id: UUID) -> list[ToolRegistryRecord]: ...

    @abstractmethod
    async def list_by_action(
        self, *, tenant_id: UUID, action_code: str
    ) -> list[ToolRegistryRecord]: ...

    @abstractmethod
    async def set_enabled(
        self, tool_id: UUID, *, tenant_id: UUID, enabled: bool
    ) -> ToolRegistryRecord: ...


class InMemoryToolRegistryRepository(ToolRegistryRepository):
    def __init__(self) -> None:
        self._tools: dict[UUID, ToolRegistryRecord] = {}

    async def insert(self, record: ToolRegistryRecord) -> ToolRegistryRecord:
        for existing in self._tools.values():
            if (
                existing.tenant_id == record.tenant_id
                and existing.tool_name == record.tool_name
                and existing.version == record.version
            ):
                raise DuplicateToolError(
                    f"Tool {record.tool_name} version {record.version} already exists"
                )
        stored = deepcopy(record)
        stored.created_at = stored.created_at or _utc_now()
        stored.updated_at = stored.updated_at or stored.created_at
        stored.agent2_tool_name = resolve_implementation(stored.implementation_key).agent2_tool_name
        self._tools[stored.id] = stored
        return deepcopy(stored)

    async def get(self, tool_id: UUID, *, tenant_id: UUID) -> ToolRegistryRecord:
        record = self._tools.get(tool_id)
        if record is None or record.tenant_id != tenant_id:
            raise ToolNotFoundError(tool_id)
        return deepcopy(record)

    async def list_tools(self, *, tenant_id: UUID) -> list[ToolRegistryRecord]:
        return sorted(
            [deepcopy(item) for item in self._tools.values() if item.tenant_id == tenant_id],
            key=lambda item: (item.tool_category.value, item.tool_name, item.version),
        )

    async def list_by_action(
        self, *, tenant_id: UUID, action_code: str
    ) -> list[ToolRegistryRecord]:
        code = action_code.strip().upper()
        return [
            deepcopy(item)
            for item in self._tools.values()
            if item.tenant_id == tenant_id and item.action_code.value == code
        ]

    async def set_enabled(
        self, tool_id: UUID, *, tenant_id: UUID, enabled: bool
    ) -> ToolRegistryRecord:
        record = await self.get(tool_id, tenant_id=tenant_id)
        record.enabled = enabled
        record.updated_at = _utc_now()
        self._tools[record.id] = deepcopy(record)
        return deepcopy(record)


class SqlAlchemyToolRegistryRepository(ToolRegistryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert(self, record: ToolRegistryRecord) -> ToolRegistryRecord:
        existing = await self._session.execute(
            select(ToolRegistryEntry).where(
                ToolRegistryEntry.tenant_id == record.tenant_id,
                ToolRegistryEntry.tool_name == record.tool_name,
                ToolRegistryEntry.version == record.version,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise DuplicateToolError(
                f"Tool {record.tool_name} version {record.version} already exists"
            )
        now = _utc_now()
        row = ToolRegistryEntry(
            id=record.id,
            tenant_id=record.tenant_id,
            tool_name=record.tool_name,
            display_name=record.display_name,
            description=record.description,
            tool_category=record.tool_category.value,
            action_code=record.action_code.value,
            implementation_key=record.implementation_key,
            version=record.version,
            enabled=record.enabled,
            requires_authorization=record.requires_authorization,
            allowed_step_types=list(record.allowed_step_types),
            required_permissions=list(record.required_permissions),
            input_schema=dict(record.input_schema),
            output_schema=dict(record.output_schema),
            configuration=dict(record.configuration),
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return _from_row(row)

    async def get(self, tool_id: UUID, *, tenant_id: UUID) -> ToolRegistryRecord:
        result = await self._session.execute(
            select(ToolRegistryEntry).where(
                ToolRegistryEntry.id == tool_id,
                ToolRegistryEntry.tenant_id == tenant_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise ToolNotFoundError(tool_id)
        return _from_row(row)

    async def list_tools(self, *, tenant_id: UUID) -> list[ToolRegistryRecord]:
        result = await self._session.execute(
            select(ToolRegistryEntry)
            .where(ToolRegistryEntry.tenant_id == tenant_id)
            .order_by(ToolRegistryEntry.tool_category, ToolRegistryEntry.tool_name)
        )
        return [_from_row(row) for row in result.scalars().all()]

    async def list_by_action(
        self, *, tenant_id: UUID, action_code: str
    ) -> list[ToolRegistryRecord]:
        result = await self._session.execute(
            select(ToolRegistryEntry).where(
                ToolRegistryEntry.tenant_id == tenant_id,
                ToolRegistryEntry.action_code == action_code.strip().upper(),
            )
        )
        return [_from_row(row) for row in result.scalars().all()]

    async def set_enabled(
        self, tool_id: UUID, *, tenant_id: UUID, enabled: bool
    ) -> ToolRegistryRecord:
        result = await self._session.execute(
            select(ToolRegistryEntry).where(
                ToolRegistryEntry.id == tool_id,
                ToolRegistryEntry.tenant_id == tenant_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise ToolNotFoundError(tool_id)
        row.enabled = enabled
        row.updated_at = _utc_now()
        await self._session.flush()
        return _from_row(row)


def record_from_input(tenant_id: UUID, payload: RegisterToolInput) -> ToolRegistryRecord:
    binding = resolve_implementation(payload.implementation_key)
    return ToolRegistryRecord(
        id=uuid4(),
        tenant_id=tenant_id,
        tool_name=payload.tool_name.strip(),
        display_name=payload.display_name,
        description=payload.description,
        tool_category=payload.tool_category,
        action_code=payload.action_code,
        implementation_key=payload.implementation_key.strip(),
        version=payload.version.strip(),
        enabled=payload.enabled,
        requires_authorization=payload.requires_authorization,
        allowed_step_types=list(payload.allowed_step_types),
        required_permissions=list(payload.required_permissions),
        input_schema=dict(payload.input_schema),
        output_schema=dict(payload.output_schema),
        configuration=dict(payload.configuration),
        agent2_tool_name=binding.agent2_tool_name,
    )


def _from_row(row: ToolRegistryEntry) -> ToolRegistryRecord:
    binding = resolve_implementation(row.implementation_key)
    return ToolRegistryRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        tool_name=row.tool_name,
        display_name=row.display_name,
        description=row.description,
        tool_category=ToolCategory(row.tool_category),
        action_code=ToolActionCode(row.action_code),
        implementation_key=row.implementation_key,
        version=row.version,
        enabled=row.enabled,
        requires_authorization=row.requires_authorization,
        allowed_step_types=list(row.allowed_step_types or []),
        required_permissions=list(row.required_permissions or []),
        input_schema=dict(row.input_schema or {}),
        output_schema=dict(row.output_schema or {}),
        configuration=dict(row.configuration or {}),
        agent2_tool_name=binding.agent2_tool_name,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
