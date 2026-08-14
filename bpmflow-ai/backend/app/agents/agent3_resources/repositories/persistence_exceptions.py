"""Persistence-specific exceptions for Agent 3 write-path storage."""

from __future__ import annotations


class PersistenceError(Exception):
    """Base class for Agent 3 persistence failures."""


class PersistenceValidationError(PersistenceError):
    """Raised when domain objects fail persistence pre-validation."""


class PersistenceConflictError(PersistenceError):
    """Raised when a conflicting persistence state is detected."""


class PersistenceLookupError(PersistenceError):
    """Raised when persisted records cannot be retrieved safely."""


class PersistenceTransactionError(PersistenceError):
    """Raised when a persistence transaction fails."""
