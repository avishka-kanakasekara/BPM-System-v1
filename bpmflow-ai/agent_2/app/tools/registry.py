"""
Agent 2 — Tool Registry (Single Source of Truth)

Maps tool name → (Python handler callable, input Pydantic schema, output Pydantic schema).
Used by function_declarations.py and the Tool Execution Engine.
"""

from typing import Any, Callable, Dict, List, Optional, Type
from pydantic import BaseModel


class ToolDefinition(BaseModel):
    """Encapsulates a registered tool's identity, description, schemas, and handler callable."""

    name: str
    description: str
    input_schema: Type[BaseModel]
    output_schema: Type[BaseModel]
    handler: Any  # Callable[[AsyncSession, BaseModel], Awaitable[BaseModel]]

    model_config = {"arbitrary_types_allowed": True}


class ToolRegistry:
    """
    Central registry mapping tool names to ToolDefinitions.
    """

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: Type[BaseModel],
        output_schema: Type[BaseModel],
        handler: Callable[..., Any],
    ) -> None:
        """Register a new tool definition."""
        name_clean = name.strip().lower()
        tool_def = ToolDefinition(
            name=name_clean,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            handler=handler,
        )
        self._tools[name_clean] = tool_def

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Retrieve a tool definition by name."""
        if not name:
            return None
        return self._tools.get(name.strip().lower())

    def list_tools(self) -> List[ToolDefinition]:
        """Return a list of all registered tool definitions."""
        return list(self._tools.values())

    def contains(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name.strip().lower() in self._tools


# Global singleton registry instance
registry = ToolRegistry()
