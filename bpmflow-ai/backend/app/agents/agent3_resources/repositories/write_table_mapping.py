"""Write-path table names and SQL for Agent 3 recommendation persistence."""

MIGRATION_0004_FILENAME = "0004_agent3_write_path_persistence.sql"

WRITE_PATH_TABLES = (
    "allocation_requests",
    "allocation_requirements",
    "allocation_recommendations",
    "allocation_candidates",
    "allocation_exclusions",
    "allocation_exclusion_reasons",
    "resource_gaps",
    "resource_alternatives",
    "budget_validation_results",
    "recommendation_evidence_links",
)

AGENT3_ALLOWED_RECOMMENDATION_STATUSES = (
    "GENERATED",
    "PENDING_HUMAN_APPROVAL",
    "SUPERSEDED",
    "FAILED",
)

SQL_SELECT_REQUEST_BY_IDEMPOTENCY = """
SELECT id, tenant_id, correlation_id
FROM allocation_requests
WHERE tenant_id = :tenant_id AND idempotency_key = :idempotency_key
"""

SQL_SELECT_RECOMMENDATION_ID_BY_REQUEST = """
SELECT id
FROM allocation_recommendations
WHERE tenant_id = :tenant_id AND request_id = :request_id
ORDER BY recommendation_version DESC
LIMIT 1
"""

SQL_SELECT_NEXT_RECOMMENDATION_VERSION = """
SELECT COALESCE(MAX(recommendation_version), 0) + 1 AS next_version
FROM allocation_recommendations
WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
"""

SQL_INSERT_ALLOCATION_REQUEST = """
INSERT INTO allocation_requests (
    id, tenant_id, idempotency_key, correlation_id, requester_id,
    evaluation_timestamp, process_instance_id, task_id,
    request_payload, request_schema_version
) VALUES (
    :id, :tenant_id, :idempotency_key, :correlation_id, :requester_id,
    :evaluation_timestamp, :process_instance_id, :task_id,
    CAST(:request_payload AS jsonb), :request_schema_version
)
ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
RETURNING id
"""

SQL_INSERT_ALLOCATION_REQUIREMENT = """
INSERT INTO allocation_requirements (
    id, tenant_id, request_id, resource_type, sequence_order,
    requester_id, task_deadline, process_stage, estimated_effort_hours,
    requirement_payload
) VALUES (
    :id, :tenant_id, :request_id, :resource_type, :sequence_order,
    :requester_id, :task_deadline, :process_stage, :estimated_effort_hours,
    CAST(:requirement_payload AS jsonb)
)
"""

SQL_INSERT_ALLOCATION_RECOMMENDATION = """
INSERT INTO allocation_recommendations (
    id, tenant_id, request_id, correlation_id, recommendation_version,
    status, requires_human_approval, manual_intervention_required,
    explanation, confidence, error_code, error_message, retryable,
    limitations, supersedes_recommendation_id, response_schema_version
) VALUES (
    :id, :tenant_id, :request_id, :correlation_id, :recommendation_version,
    :status, :requires_human_approval, :manual_intervention_required,
    :explanation, :confidence, :error_code, :error_message, :retryable,
    CAST(:limitations AS jsonb), :supersedes_recommendation_id, :response_schema_version
)
"""

SQL_INSERT_ALLOCATION_CANDIDATE = """
INSERT INTO allocation_candidates (
    tenant_id, recommendation_id, request_id, requirement_id, resource_id,
    candidate_rank, allocation_score, role_match, skill_match,
    availability_score, workload_fit, authority_match,
    current_workload_pct, projected_workload_pct,
    available_from, available_until, candidate_name
) VALUES (
    :tenant_id, :recommendation_id, :request_id, :requirement_id, :resource_id,
    :candidate_rank, :allocation_score, :role_match, :skill_match,
    :availability_score, :workload_fit, :authority_match,
    :current_workload_pct, :projected_workload_pct,
    :available_from, :available_until, :candidate_name
)
"""

SQL_INSERT_ALLOCATION_EXCLUSION = """
INSERT INTO allocation_exclusions (
    id, tenant_id, recommendation_id, request_id, requirement_id,
    resource_id, resource_type
) VALUES (
    :id, :tenant_id, :recommendation_id, :request_id, :requirement_id,
    :resource_id, :resource_type
)
RETURNING id
"""

SQL_INSERT_ALLOCATION_EXCLUSION_REASON = """
INSERT INTO allocation_exclusion_reasons (
    tenant_id, exclusion_id, sequence_order, reason_code, description, evidence_reference
) VALUES (
    :tenant_id, :exclusion_id, :sequence_order, :reason_code, :description, :evidence_reference
)
"""

SQL_INSERT_RESOURCE_GAP = """
INSERT INTO resource_gaps (
    id, tenant_id, recommendation_id, request_id, requirement_id,
    gap_type, resource_type, gap_description, eligible_count, excluded_count
) VALUES (
    :id, :tenant_id, :recommendation_id, :request_id, :requirement_id,
    :gap_type, :resource_type, :gap_description, :eligible_count, :excluded_count
)
RETURNING id
"""

SQL_INSERT_RESOURCE_ALTERNATIVE = """
INSERT INTO resource_alternatives (
    tenant_id, gap_id, recommendation_id, sequence_order,
    alternative_type, description, requires_approval,
    estimated_effort_hours, cost_impact
) VALUES (
    :tenant_id, :gap_id, :recommendation_id, :sequence_order,
    :alternative_type, :description, :requires_approval,
    :estimated_effort_hours, :cost_impact
)
"""

SQL_INSERT_BUDGET_VALIDATION = """
INSERT INTO budget_validation_results (
    tenant_id, recommendation_id, request_id, requirement_id, resource_id,
    sufficient_balance, cost_centre_match, currency_match, validity_period_valid,
    within_authorization_limit, available_balance, required_amount, validation_payload
) VALUES (
    :tenant_id, :recommendation_id, :request_id, :requirement_id, :resource_id,
    :sufficient_balance, :cost_centre_match, :currency_match, :validity_period_valid,
    :within_authorization_limit, :available_balance, :required_amount,
    CAST(:validation_payload AS jsonb)
)
"""

SQL_INSERT_EVIDENCE_LINK = """
INSERT INTO recommendation_evidence_links (
    tenant_id, recommendation_id, resource_id, evidence_reference_id,
    evidence_key, link_type, sequence_order
) VALUES (
    :tenant_id, :recommendation_id, :resource_id, :evidence_reference_id,
    :evidence_key, :link_type, :sequence_order
)
"""

SQL_MARK_SUPERSEDED = """
UPDATE allocation_recommendations
SET status = 'SUPERSEDED', updated_at = TIMEZONE('utc', NOW())
WHERE tenant_id = :tenant_id
  AND correlation_id = :correlation_id
  AND id <> :new_recommendation_id
  AND status IN ('GENERATED', 'PENDING_HUMAN_APPROVAL')
"""

SQL_SELECT_RECOMMENDATION_HEADER = """
SELECT id, tenant_id, request_id, correlation_id, recommendation_version,
       status, requires_human_approval, manual_intervention_required,
       explanation, confidence, error_code, error_message, retryable,
       limitations, response_schema_version, created_at
FROM allocation_recommendations
WHERE tenant_id = :tenant_id AND id = :recommendation_id
"""

SQL_SELECT_LATEST_RECOMMENDATION_HEADER = """
SELECT id, tenant_id, request_id, correlation_id, recommendation_version,
       status, requires_human_approval, manual_intervention_required,
       explanation, confidence, error_code, error_message, retryable,
       limitations, response_schema_version, created_at
FROM allocation_recommendations
WHERE tenant_id = :tenant_id AND correlation_id = :correlation_id
ORDER BY recommendation_version DESC, created_at DESC
LIMIT 1
"""

SQL_SELECT_REQUEST_METADATA = """
SELECT id, tenant_id, correlation_id, requester_id, evaluation_timestamp,
       process_instance_id, task_id, request_schema_version
FROM allocation_requests
WHERE tenant_id = :tenant_id AND id = :request_id
"""

SQL_SELECT_REQUIREMENTS = """
SELECT id, resource_type, sequence_order, requirement_payload
FROM allocation_requirements
WHERE tenant_id = :tenant_id AND request_id = :request_id
ORDER BY sequence_order ASC
"""

SQL_SELECT_CANDIDATES = """
SELECT requirement_id, resource_id, candidate_rank, allocation_score,
       role_match, skill_match, availability_score, workload_fit, authority_match,
       current_workload_pct, projected_workload_pct, available_from, available_until,
       candidate_name
FROM allocation_candidates
WHERE tenant_id = :tenant_id AND recommendation_id = :recommendation_id
ORDER BY requirement_id, candidate_rank ASC
"""

SQL_SELECT_EXCLUSIONS = """
SELECT e.id, e.requirement_id, e.resource_id, e.resource_type,
       r.sequence_order, r.reason_code, r.description, r.evidence_reference
FROM allocation_exclusions e
JOIN allocation_exclusion_reasons r
  ON r.tenant_id = e.tenant_id AND r.exclusion_id = e.id
WHERE e.tenant_id = :tenant_id AND e.recommendation_id = :recommendation_id
ORDER BY e.requirement_id, e.resource_id, r.sequence_order ASC
"""

SQL_SELECT_GAPS = """
SELECT id, requirement_id, gap_type, resource_type, gap_description,
       eligible_count, excluded_count
FROM resource_gaps
WHERE tenant_id = :tenant_id AND recommendation_id = :recommendation_id
ORDER BY id ASC
"""

SQL_SELECT_ALTERNATIVES = """
SELECT gap_id, sequence_order, alternative_type, description,
       requires_approval, estimated_effort_hours, cost_impact
FROM resource_alternatives
WHERE tenant_id = :tenant_id AND recommendation_id = :recommendation_id
ORDER BY gap_id, sequence_order ASC
"""

SQL_SELECT_BUDGET_VALIDATIONS = """
SELECT requirement_id, resource_id, sufficient_balance, cost_centre_match,
       currency_match, validity_period_valid, within_authorization_limit,
       available_balance, required_amount, validation_payload
FROM budget_validation_results
WHERE tenant_id = :tenant_id AND recommendation_id = :recommendation_id
"""

SQL_SELECT_EVIDENCE_LINKS = """
SELECT resource_id, evidence_key, link_type, sequence_order
FROM recommendation_evidence_links
WHERE tenant_id = :tenant_id AND recommendation_id = :recommendation_id
ORDER BY sequence_order ASC
"""
