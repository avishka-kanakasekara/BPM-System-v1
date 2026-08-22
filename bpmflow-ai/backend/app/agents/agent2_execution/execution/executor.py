"""
Agent 2 — Tool Executor

Invokes a Tool-Guard-approved tool call via the central ToolRegistry,
times execution latency, and captures the result payload or exception.
Represents the ACT step plus the first half of OBSERVE in the cognitive cycle.
"""

import time
from typing import Any, Dict, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.tools.registry import registry


async def execute_tool(
    session: Optional[AsyncSession],
    tool_name: str,
    parameters: Dict[str, Any],
) -> Tuple[bool, Dict[str, Any], int, str]:
    """
    Execute an approved tool call via ToolRegistry.

    :param session: Active AsyncSession (optional)
    :param tool_name: Name of tool to execute
    :param parameters: Dict of arguments
    :return: Tuple of (success: bool, result_dict: dict, latency_ms: int, error_message: str)
    """
    tool_def = registry.get(tool_name)
    if not tool_def:
        return False, {}, 0, f"Tool {tool_name!r} not found in ToolRegistry"

    # Validate parameters into target Pydantic input schema
    try:
        validated_input = tool_def.input_schema.model_validate(parameters)
    except Exception as ve:
        return False, {}, 0, f"Parameter schema validation error: {str(ve)}"

    start_time = time.perf_counter()
    try:
        # Invoke async tool handler
        output_obj = await tool_def.handler(session, validated_input)
        latency_ms = int((time.perf_counter() - start_time) * 1000)

        # Convert output model to dict payload
        result_dict = (
            output_obj.model_dump() if hasattr(output_obj, "model_dump") else dict(output_obj)
        )
        return True, result_dict, latency_ms, ""

    except Exception as exc:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        error_msg = str(exc) or exc.__class__.__name__
        return False, {}, latency_ms, error_msg
