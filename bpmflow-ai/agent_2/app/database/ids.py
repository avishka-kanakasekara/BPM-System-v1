"""Deterministic ID helpers for Agent 2 persistence."""

from __future__ import annotations

import uuid
from typing import Optional


def parse_uuid(value: Optional[str]) -> uuid.UUID:
    """
    Convert a process/task identifier into a UUID.

    Real UUIDs are preserved. Non-UUID strings (e.g. proc-api-1001) map to a
    stable UUID5 so receipts, tasks, and process rows stay linked.
    """
    if not value:
        return uuid.uuid4()
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return uuid.uuid5(uuid.NAMESPACE_DNS, f"bpmflow.agent2.{value}")
