"""
Sanitize Agent 2 execution explanations for frontend/API exposure.

Never expose raw chain-of-thought, system prompts, API keys, or hidden policies.
"""

from __future__ import annotations

from typing import Any

from app.core.redaction import redact_text as _redact_text


def _sanitize_event(event: Any) -> dict[str, Any]:
    if not isinstance(event, dict):
        return {"summary": _redact_text(str(event))}
    return {
        "tool": event.get("tool"),
        "status": event.get("status"),
        "latency_ms": event.get("latency_ms"),
        "error": _redact_text(str(event.get("error") or ""))[:500],
    }


def sanitize_execution_explanation(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a safe execution explanation for clients."""
    events = raw.get("execution_events") or []
    safe_events: list[dict[str, Any]] = []
    if isinstance(events, list):
        safe_events = [_sanitize_event(e) for e in events[:20]]

    return {
        "receipt_status": raw.get("receipt_status"),
        "tool_name": raw.get("tool_name"),
        "decision_reason": _redact_text(str(raw.get("decision_reason") or ""))[:1000],
        "plan_summary": _redact_text(str(raw.get("plan_reasoning") or ""))[:1000],
        "tools_executed": raw.get("tools_executed") or [],
        "critic_notes": _redact_text(str(raw.get("critic_notes") or ""))[:500],
        "execution_events": safe_events,
        "total_score": raw.get("total_score"),
        "score_breakdown": raw.get("score_breakdown") or {},
    }
