"""Tenant-scoped Tool Registry service. Resolves tools; does not execute them."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from .exceptions import (
    ToolAmbiguousError,
    ToolCategoryMismatchError,
    ToolDisabledError,
    ToolNotRegisteredError,
    ToolRegistryError,
    ToolStepTypeNotAllowedError,
    UnknownImplementationError,
)
from .implementations import resolve_implementation
from .repository import ToolRegistryRepository, record_from_input
from .schemas import RegisterToolInput, ToolRegistryRecord
from .validator import ToolRegistryValidator


class ToolRegistryService:
    def __init__(
        self,
        repository: ToolRegistryRepository,
        *,
        validator: ToolRegistryValidator | None = None,
    ) -> None:
        self._repo = repository
        self._validator = validator or ToolRegistryValidator()

    async def register_tool(
        self, payload: RegisterToolInput, *, tenant_id: UUID
    ) -> ToolRegistryRecord:
        result = self._validator.validate_registration(payload)
        if not result.valid:
            first = result.issues[0]
            raise ToolRegistryError(first.message, error_code=first.code)
        if payload.enabled:
            existing = await self._repo.list_by_action(
                tenant_id=tenant_id, action_code=payload.action_code.value
            )
            if any(item.enabled for item in existing):
                raise ToolAmbiguousError(
                    "Another enabled tool already exists for this action_code"
                )
        record = record_from_input(tenant_id, payload)
        return await self._repo.insert(record)

    async def get_tool(self, tool_id: UUID, *, tenant_id: UUID) -> ToolRegistryRecord:
        return await self._repo.get(tool_id, tenant_id=tenant_id)

    async def list_tools(self, *, tenant_id: UUID) -> list[ToolRegistryRecord]:
        return await self._repo.list_tools(tenant_id=tenant_id)

    async def enable_tool(self, tool_id: UUID, *, tenant_id: UUID) -> ToolRegistryRecord:
        current = await self._repo.get(tool_id, tenant_id=tenant_id)
        others = await self._repo.list_by_action(
            tenant_id=tenant_id, action_code=current.action_code.value
        )
        if any(item.enabled and item.id != tool_id for item in others):
            raise ToolAmbiguousError(
                "Disable the currently enabled version before enabling another"
            )
        return await self._repo.set_enabled(tool_id, tenant_id=tenant_id, enabled=True)

    async def disable_tool(self, tool_id: UUID, *, tenant_id: UUID) -> ToolRegistryRecord:
        return await self._repo.set_enabled(tool_id, tenant_id=tenant_id, enabled=False)

    async def validate_tool(self, payload: RegisterToolInput):
        return self._validator.validate_registration(payload)

    async def resolve_action(
        self,
        *,
        tenant_id: UUID,
        action_code: str,
        tool_category: str | None = None,
        step_type: str | None = None,
    ) -> ToolRegistryRecord:
        code = (action_code or "").strip().upper()
        if not code:
            raise ToolNotRegisteredError("action_code is required")
        matches = await self._repo.list_by_action(tenant_id=tenant_id, action_code=code)
        if not matches:
            raise ToolNotRegisteredError(f"No tool registered for action {code}")
        enabled = [item for item in matches if item.enabled]
        if not enabled:
            raise ToolDisabledError(f"Tool for action {code} is disabled")
        if tool_category:
            category = tool_category.strip().upper()
            categorized = [item for item in enabled if item.tool_category.value == category]
            if not categorized:
                raise ToolCategoryMismatchError(
                    f"No enabled tool for {code} in category {category}"
                )
            enabled = categorized
        if step_type:
            step = step_type.strip().upper()
            typed = [
                item
                for item in enabled
                if not item.allowed_step_types or step in {value.upper() for value in item.allowed_step_types}
            ]
            if not typed:
                raise ToolStepTypeNotAllowedError(
                    f"Step type {step} is not allowed for action {code}"
                )
            enabled = typed
        if len(enabled) > 1:
            raise ToolAmbiguousError(
                f"Multiple enabled tools match action {code}; disable extras or refine filters"
            )
        return enabled[0]

    async def resolve_for_step(
        self, *, tenant_id: UUID, workflow_step: Any
    ) -> ToolRegistryRecord:
        action = getattr(workflow_step, "required_action", None)
        category = getattr(workflow_step, "required_tool_category", None)
        step_type = getattr(workflow_step, "step_type", None)
        step_type_value = getattr(step_type, "value", step_type)
        return await self.resolve_action(
            tenant_id=tenant_id,
            action_code=str(action or ""),
            tool_category=str(category) if category else None,
            step_type=str(step_type_value) if step_type_value else None,
        )

    def implementation_for(self, record: ToolRegistryRecord):
        try:
            return resolve_implementation(record.implementation_key)
        except KeyError as exc:
            raise UnknownImplementationError(
                f"implementation_key {record.implementation_key!r} is not allow-listed"
            ) from exc
