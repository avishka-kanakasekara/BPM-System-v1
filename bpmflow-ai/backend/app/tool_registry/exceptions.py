"""Tool Registry errors. Resolution is not execution."""

from uuid import UUID


class ToolRegistryError(ValueError):
    error_code = "TOOL_REGISTRY_ERROR"

    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        self.error_code = error_code or self.error_code
        super().__init__(message)

    def as_dict(self) -> dict[str, object]:
        return {"error_code": self.error_code, "message": str(self)}


class ToolNotFoundError(KeyError):
    def __init__(self, tool_id: UUID) -> None:
        self.tool_id = tool_id
        super().__init__(f"Unknown tool: {tool_id}")


class ToolNotRegisteredError(ToolRegistryError):
    error_code = "TOOL_NOT_REGISTERED"


class ToolDisabledError(ToolRegistryError):
    error_code = "TOOL_DISABLED"


class ToolAmbiguousError(ToolRegistryError):
    error_code = "TOOL_AMBIGUOUS"


class ToolCategoryMismatchError(ToolRegistryError):
    error_code = "TOOL_CATEGORY_MISMATCH"


class ToolStepTypeNotAllowedError(ToolRegistryError):
    error_code = "TOOL_STEP_TYPE_NOT_ALLOWED"


class UnknownImplementationError(ToolRegistryError):
    error_code = "UNKNOWN_IMPLEMENTATION"


class SecretInConfigurationError(ToolRegistryError):
    error_code = "SECRET_NOT_ALLOWED"


class DuplicateToolError(ToolRegistryError):
    error_code = "DUPLICATE_TOOL"


class CrossTenantToolError(ToolRegistryError):
    error_code = "CROSS_TENANT_DENIED"
