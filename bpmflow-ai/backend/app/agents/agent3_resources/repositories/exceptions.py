"""Repository-specific exceptions for Agent 3 persistence."""


class MappingError(Exception):
    """Raised when database rows cannot be mapped into Agent 3 evidence models."""


class CrossTenantGraphError(MappingError):
    """Raised when related rows span multiple tenants."""


class MissingEvidenceError(MappingError):
    """Raised when required evidence rows are absent for mapping."""
