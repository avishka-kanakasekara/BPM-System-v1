"""Deterministic Tool Registry validation. No LLM. No arbitrary code."""

from __future__ import annotations

from typing import Any

from .constants import ALLOWED_STEP_TYPES, SECRET_KEY_FRAGMENTS, ToolActionCode, ToolCategory
from .implementations import is_registered_implementation
from .schemas import RegisterToolInput, ToolValidationResult, ValidationIssue


class ToolRegistryValidator:
    def validate_registration(self, payload: RegisterToolInput) -> ToolValidationResult:
        issues: list[ValidationIssue] = []
        if not (payload.tool_name or "").strip():
            issues.append(ValidationIssue(code="INVALID_TOOL_NAME", message="tool_name is required", field="tool_name"))
        if not (payload.version or "").strip():
            issues.append(ValidationIssue(code="INVALID_VERSION", message="version is required", field="version"))
        try:
            ToolCategory(payload.tool_category)
        except ValueError:
            issues.append(
                ValidationIssue(code="INVALID_CATEGORY", message="tool_category is not allowed", field="tool_category")
            )
        try:
            ToolActionCode(payload.action_code)
        except ValueError:
            issues.append(
                ValidationIssue(code="INVALID_ACTION_CODE", message="action_code is not allowed", field="action_code")
            )
        if not is_registered_implementation(payload.implementation_key):
            issues.append(
                ValidationIssue(
                    code="UNKNOWN_IMPLEMENTATION",
                    message="implementation_key is not in the safe allow-list",
                    field="implementation_key",
                )
            )
        for step_type in payload.allowed_step_types:
            if step_type not in ALLOWED_STEP_TYPES:
                issues.append(
                    ValidationIssue(
                        code="INVALID_STEP_TYPE",
                        message=f"allowed_step_types contains unknown type {step_type}",
                        field="allowed_step_types",
                    )
                )
        for perm in payload.required_permissions:
            if not isinstance(perm, str) or not perm.strip():
                issues.append(
                    ValidationIssue(
                        code="INVALID_PERMISSIONS",
                        message="required_permissions must be non-empty strings",
                        field="required_permissions",
                    )
                )
        issues.extend(self._json_schema(payload.input_schema, "input_schema"))
        issues.extend(self._json_schema(payload.output_schema, "output_schema"))
        if self._contains_secret(payload.configuration) or self._contains_secret(payload.input_schema) or self._contains_secret(payload.output_schema):
            issues.append(
                ValidationIssue(
                    code="SECRET_NOT_ALLOWED",
                    message="Secrets must not be stored in the tool registry",
                    field="configuration",
                )
            )
        return ToolValidationResult(valid=not issues, issues=issues)

    def _json_schema(self, value: Any, field: str) -> list[ValidationIssue]:
        if not isinstance(value, dict):
            return [ValidationIssue(code="INVALID_JSON_SCHEMA", message=f"{field} must be an object", field=field)]
        schema_type = value.get("type")
        if schema_type not in {None, "object", "array"} and "properties" not in value:
            return [
                ValidationIssue(
                    code="INVALID_JSON_SCHEMA",
                    message=f"{field} must be a JSON Schema object",
                    field=field,
                )
            ]
        if schema_type is None and "properties" not in value and "$schema" not in value:
            return [
                ValidationIssue(
                    code="INVALID_JSON_SCHEMA",
                    message=f"{field} must declare type or properties",
                    field=field,
                )
            ]
        return []

    def _contains_secret(self, value: Any) -> bool:
        if isinstance(value, dict):
            for key, item in value.items():
                lowered = str(key).lower()
                if any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS):
                    return True
                if self._contains_secret(item):
                    return True
            return False
        if isinstance(value, list):
            return any(self._contains_secret(item) for item in value)
        return False
