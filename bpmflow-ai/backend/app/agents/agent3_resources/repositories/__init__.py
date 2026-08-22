"""Agent 3 PostgreSQL repository adapters."""

from .exceptions import CrossTenantGraphError, MappingError, MissingEvidenceError
from .postgres_resource_repository import PostgresResourceRepository
from .seed_constants import (
    AGENT3_DEMO_TENANT_CODE,
    AGENT3_DEMO_TENANT_ID,
    MIGRATION_0003_FILENAME,
    SEED_EVALUATION_TIMESTAMP,
)
from .session_factory import (
    create_async_session_factory,
    create_postgres_resource_repository,
    normalize_async_database_url,
)
from .table_mapping import (
    AGENT3_RECOMMENDATION_STATUSES,
    ALLOWED_RESOURCE_TYPES,
    LEGACY_DEMO_TENANT_CODE,
    LEGACY_DEMO_TENANT_ID,
    MIGRATION_0002_FILENAME,
    READ_PATH_TABLES,
)
from .persistence_exceptions import (
    PersistenceError,
    PersistenceValidationError,
    PersistenceConflictError,
    PersistenceLookupError,
    PersistenceTransactionError,
)
from .write_table_mapping import (
    MIGRATION_0004_FILENAME,
    WRITE_PATH_TABLES,
    AGENT3_ALLOWED_RECOMMENDATION_STATUSES,
)
from .write_mappers import (
    map_request_to_allocation_request,
    map_requirement_to_allocation_requirement,
    map_recommendation_to_allocation_recommendation,
    map_candidate_to_allocation_candidate,
    map_exclusion_to_allocation_exclusion,
    map_exclusion_reason_to_allocation_exclusion_reason,
    map_gap_to_resource_gap,
    map_alternative_to_resource_alternative,
    map_budget_validation_to_budget_validation_result,
    map_evidence_link_to_recommendation_evidence_link,
)
from .recommendation_repository import RecommendationWriteRepository

__all__ = [
    "PostgresResourceRepository",
    "MappingError",
    "CrossTenantGraphError",
    "MissingEvidenceError",
    "create_async_session_factory",
    "create_postgres_resource_repository",
    "normalize_async_database_url",
    "MIGRATION_0002_FILENAME",
    "MIGRATION_0003_FILENAME",
    "MIGRATION_0004_FILENAME",
    "READ_PATH_TABLES",
    "WRITE_PATH_TABLES",
    "ALLOWED_RESOURCE_TYPES",
    "AGENT3_RECOMMENDATION_STATUSES",
    "AGENT3_ALLOWED_RECOMMENDATION_STATUSES",
    "LEGACY_DEMO_TENANT_ID",
    "LEGACY_DEMO_TENANT_CODE",
    "AGENT3_DEMO_TENANT_ID",
    "AGENT3_DEMO_TENANT_CODE",
    "SEED_EVALUATION_TIMESTAMP",
    "PersistenceError",
    "PersistenceValidationError",
    "PersistenceConflictError",
    "PersistenceLookupError",
    "PersistenceTransactionError",
    "RecommendationWriteRepository",
    "map_request_to_allocation_request",
    "map_requirement_to_allocation_requirement",
    "map_recommendation_to_allocation_recommendation",
    "map_candidate_to_allocation_candidate",
    "map_exclusion_to_allocation_exclusion",
    "map_exclusion_reason_to_allocation_exclusion_reason",
    "map_gap_to_resource_gap",
    "map_alternative_to_resource_alternative",
    "map_budget_validation_to_budget_validation_result",
    "map_evidence_link_to_recommendation_evidence_link",
]
