"""Structured missing-data errors for canonical process context."""

from __future__ import annotations


class MissingRequiredContextError(ValueError):
    """Required business fact is absent. Never invent a replacement value."""

    error_code = "MISSING_REQUIRED_CONTEXT"

    def __init__(self, field: str, *, missing_fields: list[str] | None = None) -> None:
        self.field = field
        self.missing_fields = missing_fields or [field]
        super().__init__(
            f"{self.error_code} field={self.field} missing={','.join(self.missing_fields)}"
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "error_code": self.error_code,
            "field": self.field,
            "missing_fields": self.missing_fields,
        }
