"""Standard API error shapes for BPMFlow AI."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Structured error detail (validation, domain, or infrastructure)."""

    code: str = Field(..., min_length=1, description="Stable machine-readable error code")
    message: str = Field(..., min_length=1, description="Human-readable explanation")
    field: str | None = Field(default=None, description="Optional field path for validation errors")
    context: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """FastAPI-compatible error body — use as ``detail`` payload."""

    detail: str | ErrorDetail | list[ErrorDetail]

    @classmethod
    def from_code(cls, code: str, message: str, **context: Any) -> ErrorResponse:
        return cls(detail=ErrorDetail(code=code, message=message, context=context or {}))

    @classmethod
    def from_message(cls, message: str) -> ErrorResponse:
        return cls(detail=message)
