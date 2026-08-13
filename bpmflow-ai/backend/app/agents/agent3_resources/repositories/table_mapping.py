"""SQL table and column names for Agent 3 read-path persistence."""

LEGACY_DEMO_TENANT_ID = "00000000-0000-0000-0000-000000000099"
LEGACY_DEMO_TENANT_CODE = "LEGACY_DEMO"

MIGRATION_0002_FILENAME = "0002_agent3_resource_persistence.sql"

READ_PATH_TABLES = (
    "tenants",
    "roles",
    "skills",
    "authorities",
    "resource_roles",
    "resource_skills",
    "resource_authorities",
    "human_resource_profiles",
    "budget_resource_profiles",
    "resource_availability",
    "workload_snapshots",
    "sod_rules",
    "resource_declared_conflicts",
    "evidence_references",
)

ALLOWED_RESOURCE_TYPES = (
    "HUMAN",
    "BUDGET",
    "SYSTEM",
    "EQUIPMENT",
    "EXTERNAL_SERVICE",
)

AGENT3_RECOMMENDATION_STATUSES = (
    "GENERATED",
    "PENDING_HUMAN_APPROVAL",
    "SUPERSEDED",
    "FAILED",
)

SQL_SELECT_HUMAN_RESOURCES = """
SELECT id, tenant_id, name, is_active
FROM resources
WHERE tenant_id = :tenant_id AND type = 'HUMAN'
ORDER BY id ASC
"""

SQL_SELECT_BUDGET_RESOURCES = """
SELECT id, tenant_id, name, is_active
FROM resources
WHERE tenant_id = :tenant_id AND type = 'BUDGET'
ORDER BY id ASC
"""

SQL_SELECT_RESOURCE_ROLES = """
SELECT rr.resource_id, rr.tenant_id, r.code
FROM resource_roles rr
JOIN roles r ON r.tenant_id = rr.tenant_id AND r.id = rr.role_id
WHERE rr.tenant_id = :tenant_id AND rr.resource_id = ANY(:resource_ids)
ORDER BY rr.resource_id, r.code
"""

SQL_SELECT_RESOURCE_SKILLS = """
SELECT rs.resource_id, rs.tenant_id, s.code
FROM resource_skills rs
JOIN skills s ON s.tenant_id = rs.tenant_id AND s.id = rs.skill_id
WHERE rs.tenant_id = :tenant_id AND rs.resource_id = ANY(:resource_ids)
ORDER BY rs.resource_id, s.code
"""

SQL_SELECT_RESOURCE_AUTHORITIES = """
SELECT ra.resource_id, ra.tenant_id, a.code
FROM resource_authorities ra
JOIN authorities a ON a.tenant_id = ra.tenant_id AND a.id = ra.authority_id
WHERE ra.tenant_id = :tenant_id AND ra.resource_id = ANY(:resource_ids)
  AND ra.granted_at <= :evaluation_timestamp
  AND (ra.valid_until IS NULL OR ra.valid_until >= :evaluation_timestamp)
ORDER BY ra.resource_id, a.code
"""

SQL_SELECT_HUMAN_PROFILES = """
SELECT tenant_id, resource_id, max_workload_pct, evidence_checked_at, evidence_valid_until
FROM human_resource_profiles
WHERE tenant_id = :tenant_id AND resource_id = ANY(:resource_ids)
"""

SQL_SELECT_BUDGET_PROFILES = """
SELECT tenant_id, resource_id, cost_centre, currency, available_balance,
       authorization_limit, valid_from, valid_until, evidence_checked_at, evidence_valid_until
FROM budget_resource_profiles
WHERE tenant_id = :tenant_id AND resource_id = ANY(:resource_ids)
"""

SQL_SELECT_AVAILABILITY = """
SELECT tenant_id, resource_id, available_from, available_until
FROM resource_availability
WHERE tenant_id = :tenant_id AND resource_id = ANY(:resource_ids)
  AND available_from <= :evaluation_timestamp
  AND (available_until IS NULL OR available_until >= :evaluation_timestamp)
ORDER BY resource_id, available_from
"""

SQL_SELECT_WORKLOAD_SNAPSHOTS = """
SELECT tenant_id, resource_id, snapshot_at, current_workload_pct, max_workload_pct
FROM workload_snapshots
WHERE tenant_id = :tenant_id AND resource_id = ANY(:resource_ids)
  AND snapshot_at <= :evaluation_timestamp
ORDER BY resource_id, snapshot_at DESC
"""

SQL_SELECT_DECLARED_CONFLICTS = """
SELECT tenant_id, resource_id, conflicting_resource_id, conflict_flag_code
FROM resource_declared_conflicts
WHERE tenant_id = :tenant_id AND resource_id = ANY(:resource_ids)
  AND valid_from <= :evaluation_timestamp
  AND (valid_until IS NULL OR valid_until >= :evaluation_timestamp)
"""

SQL_SELECT_EVIDENCE_REFERENCES = """
SELECT tenant_id, resource_id, evidence_key, payload, checked_at, valid_until
FROM evidence_references
WHERE tenant_id = :tenant_id AND resource_id = ANY(:resource_ids)
  AND checked_at <= :evaluation_timestamp
  AND valid_until >= :evaluation_timestamp
ORDER BY resource_id, evidence_key
"""
