"""Pydantic records for the DB Tool Registry (contracts, not execution)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from .constants import ToolActionCode, ToolCategory


class ToolRegistryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    tool_name: str
    display_name: str | None = None
    description: str | None = None
    tool_category: ToolCategory
    action_code: ToolActionCode
    implementation_key: str
    version: str = "1"
    enabled: bool = True
    requires_authorization: bool = True
    allowed_step_types: list[str] = Field(default_factory=list)
    required_permissions: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    output_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    configuration: dict[str, Any] = Field(default_factory=dict)
    agent2_tool_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RegisterToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    display_name: str | None = None
    description: str | None = None
    tool_category: ToolCategory
    action_code: ToolActionCode
    implementation_key: str
    version: str = "1"
    enabled: bool = True
    requires_authorization: bool = True
    allowed_step_types: list[str] = Field(default_factory=list)
    required_permissions: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    output_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    configuration: dict[str, Any] = Field(default_factory=dict)


class ResolveToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_code: str
    tool_category: str | None = None
    step_type: str | None = None


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    field: str | None = None


class ToolValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
