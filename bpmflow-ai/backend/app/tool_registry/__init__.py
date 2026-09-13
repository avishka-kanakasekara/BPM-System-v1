"""DB-backed Tool Registry owned for Agent 4 declarations and future Agent 2 execution."""

from .constants import ToolActionCode, ToolCategory
from .exceptions import (
    ToolAmbiguousError,
    ToolCategoryMismatchError,
    ToolDisabledError,
    ToolNotFoundError,
    ToolNotRegisteredError,
    ToolRegistryError,
    ToolStepTypeNotAllowedError,
    UnknownImplementationError,
)
from .implementations import REGISTERED_IMPLEMENTATIONS, resolve_implementation
from .repository import InMemoryToolRegistryRepository, SqlAlchemyToolRegistryRepository
from .schemas import RegisterToolInput, ResolveToolInput, ToolRegistryRecord
from .seed import seed_bpmflow_tool_registry
from .service import ToolRegistryService
from .validator import ToolRegistryValidator

__all__ = [
    "ToolActionCode",
    "ToolCategory",
    "ToolAmbiguousError",
    "ToolCategoryMismatchError",
    "ToolDisabledError",
    "ToolNotFoundError",
    "ToolNotRegisteredError",
    "ToolRegistryError",
    "ToolStepTypeNotAllowedError",
    "UnknownImplementationError",
    "REGISTERED_IMPLEMENTATIONS",
    "resolve_implementation",
    "InMemoryToolRegistryRepository",
    "SqlAlchemyToolRegistryRepository",
    "RegisterToolInput",
    "ResolveToolInput",
    "ToolRegistryRecord",
    "seed_bpmflow_tool_registry",
    "ToolRegistryService",
    "ToolRegistryValidator",
]
