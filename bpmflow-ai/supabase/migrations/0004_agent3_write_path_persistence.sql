-- Agent 3 write-path recommendation persistence
-- Migration number 0004 — Agent 3 owned
--
-- Agent 3 is advisory only. Human approval (APPROVED/REJECTED) happens outside Agent 3.
-- Business constraint outcomes are not technical failures.
-- requester_id identifies the requester; it is never tenant_id.
-- RLS is enabled on all tables, but runtime JWT tenant policies are not implemented in this migration.
-- FAILED recommendations have no candidates/gaps/alternatives/confidence enforced by repository logic,
-- not fully by parent-table CHECK constraint alone.
-- Business-gap status semantics are enforced by domain validation plus repository logic.

-- =============================================================================
-- A. allocation_requests
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.allocation_requests (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES public.tenants(id),
    idempotency_key TEXT NOT NULL,
    correlation_id UUID NOT NULL,
    requester_id UUID NOT NULL,
    evaluation_timestamp TIMESTAMPTZ NOT NULL,
    process_instance_id UUID,
    task_id UUID,
    request_payload JSONB NOT NULL,
    request_schema_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    CONSTRAINT allocation_requests_tenant_idempotency_unique UNIQUE (tenant_id, idempotency_key),
    CONSTRAINT allocation_requests_tenant_id_unique UNIQUE (tenant_id, id)
);

CREATE TRIGGER update_allocation_requests_updated_at
    BEFORE UPDATE ON public.allocation_requests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- B. allocation_requirements
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.allocation_requirements (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    request_id UUID NOT NULL,
    resource_type TEXT NOT NULL,
    sequence_order INTEGER NOT NULL,
    requester_id UUID NOT NULL,
    task_deadline TIMESTAMPTZ NOT NULL,
    process_stage TEXT NOT NULL,
    estimated_effort_hours NUMERIC(18, 2),
    requirement_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    CONSTRAINT allocation_requirements_resource_type_check
        CHECK (resource_type IN ('HUMAN', 'BUDGET')),
    CONSTRAINT allocation_requirements_sequence_positive
        CHECK (sequence_order >= 1),
    CONSTRAINT allocation_requirements_request_fkey
        FOREIGN KEY (tenant_id, request_id)
        REFERENCES public.allocation_requests(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT allocation_requirements_tenant_request_sequence_unique
        UNIQUE (tenant_id, request_id, sequence_order),
    CONSTRAINT allocation_requirements_tenant_id_unique UNIQUE (tenant_id, id)
);

-- =============================================================================
-- C. allocation_recommendations
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.allocation_recommendations (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    request_id UUID NOT NULL,
    correlation_id UUID NOT NULL,
    recommendation_version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL,
    requires_human_approval BOOLEAN NOT NULL,
    manual_intervention_required BOOLEAN NOT NULL,
    explanation TEXT NOT NULL DEFAULT '',
    confidence NUMERIC(5, 4),
    error_code TEXT,
    error_message TEXT,
    retryable BOOLEAN,
    limitations JSONB NOT NULL DEFAULT '[]'::jsonb,
    supersedes_recommendation_id UUID,
    response_schema_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    CONSTRAINT allocation_recommendations_status_check
        CHECK (status IN ('GENERATED', 'PENDING_HUMAN_APPROVAL', 'SUPERSEDED', 'FAILED')),
    CONSTRAINT allocation_recommendations_confidence_range
        CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    CONSTRAINT allocation_recommendations_version_positive
        CHECK (recommendation_version >= 1),
    CONSTRAINT allocation_recommendations_business_shape CHECK (
        (
            status IN ('GENERATED', 'PENDING_HUMAN_APPROVAL', 'SUPERSEDED')
            AND requires_human_approval = TRUE
            AND manual_intervention_required = FALSE
            AND btrim(explanation) <> ''
            AND confidence IS NOT NULL
            AND error_code IS NULL
            AND error_message IS NULL
            AND retryable IS NULL
        )
        OR (
            status = 'FAILED'
            AND requires_human_approval = FALSE
            AND manual_intervention_required = TRUE
            AND error_code IS NOT NULL
            AND btrim(error_code) <> ''
            AND error_message IS NOT NULL
            AND btrim(error_message) <> ''
            AND retryable IS NOT NULL
            AND confidence IS NULL
        )
    ),
    CONSTRAINT allocation_recommendations_request_fkey
        FOREIGN KEY (tenant_id, request_id)
        REFERENCES public.allocation_requests(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT allocation_recommendations_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT allocation_recommendations_supersedes_fkey
        FOREIGN KEY (tenant_id, supersedes_recommendation_id)
        REFERENCES public.allocation_recommendations(tenant_id, id)
);

CREATE TRIGGER update_allocation_recommendations_updated_at
    BEFORE UPDATE ON public.allocation_recommendations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- D. allocation_candidates
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.allocation_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    recommendation_id UUID NOT NULL,
    request_id UUID NOT NULL,
    requirement_id UUID NOT NULL,
    resource_id UUID NOT NULL,
    candidate_rank INTEGER NOT NULL,
    allocation_score NUMERIC(5, 4) NOT NULL,
    role_match NUMERIC(5, 4) NOT NULL,
    skill_match NUMERIC(5, 4) NOT NULL,
    availability_score NUMERIC(5, 4) NOT NULL,
    workload_fit NUMERIC(5, 4) NOT NULL,
    authority_match NUMERIC(5, 4) NOT NULL,
    current_workload_pct NUMERIC(5, 2) NOT NULL,
    projected_workload_pct NUMERIC(5, 2) NOT NULL,
    available_from TIMESTAMPTZ NOT NULL,
    available_until TIMESTAMPTZ,
    candidate_name TEXT NOT NULL,
    CONSTRAINT allocation_candidates_rank_positive CHECK (candidate_rank >= 1),
    CONSTRAINT allocation_candidates_scores_range CHECK (
        allocation_score >= 0 AND allocation_score <= 1
        AND role_match >= 0 AND role_match <= 1
        AND skill_match >= 0 AND skill_match <= 1
        AND availability_score >= 0 AND availability_score <= 1
        AND workload_fit >= 0 AND workload_fit <= 1
        AND authority_match >= 0 AND authority_match <= 1
    ),
    CONSTRAINT allocation_candidates_workload_range CHECK (
        current_workload_pct >= 0 AND current_workload_pct <= 100
        AND projected_workload_pct >= 0 AND projected_workload_pct <= 100
    ),
    CONSTRAINT allocation_candidates_recommendation_fkey
        FOREIGN KEY (tenant_id, recommendation_id)
        REFERENCES public.allocation_recommendations(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT allocation_candidates_request_fkey
        FOREIGN KEY (tenant_id, request_id)
        REFERENCES public.allocation_requests(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT allocation_candidates_requirement_fkey
        FOREIGN KEY (tenant_id, requirement_id)
        REFERENCES public.allocation_requirements(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT allocation_candidates_resource_fkey
        FOREIGN KEY (tenant_id, resource_id)
        REFERENCES public.resources(tenant_id, id),
    CONSTRAINT allocation_candidates_tenant_rec_req_rank_unique
        UNIQUE (tenant_id, recommendation_id, requirement_id, candidate_rank)
);

-- =============================================================================
-- E. allocation_exclusions and reasons
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.allocation_exclusions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    recommendation_id UUID NOT NULL,
    request_id UUID NOT NULL,
    requirement_id UUID NOT NULL,
    resource_id UUID NOT NULL,
    resource_type TEXT NOT NULL,
    CONSTRAINT allocation_exclusions_resource_type_check
        CHECK (resource_type IN ('HUMAN', 'BUDGET', 'SYSTEM', 'EQUIPMENT', 'EXTERNAL_SERVICE')),
    CONSTRAINT allocation_exclusions_recommendation_fkey
        FOREIGN KEY (tenant_id, recommendation_id)
        REFERENCES public.allocation_recommendations(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT allocation_exclusions_request_fkey
        FOREIGN KEY (tenant_id, request_id)
        REFERENCES public.allocation_requests(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT allocation_exclusions_requirement_fkey
        FOREIGN KEY (tenant_id, requirement_id)
        REFERENCES public.allocation_requirements(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT allocation_exclusions_resource_fkey
        FOREIGN KEY (tenant_id, resource_id)
        REFERENCES public.resources(tenant_id, id),
    CONSTRAINT allocation_exclusions_tenant_rec_req_resource_unique
        UNIQUE (tenant_id, recommendation_id, requirement_id, resource_id),
    CONSTRAINT allocation_exclusions_tenant_id_unique UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS public.allocation_exclusion_reasons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    exclusion_id UUID NOT NULL,
    sequence_order INTEGER NOT NULL,
    reason_code TEXT NOT NULL,
    description TEXT NOT NULL,
    evidence_reference TEXT,
    CONSTRAINT allocation_exclusion_reasons_sequence_positive
        CHECK (sequence_order >= 1),
    CONSTRAINT allocation_exclusion_reasons_exclusion_fkey
        FOREIGN KEY (tenant_id, exclusion_id)
        REFERENCES public.allocation_exclusions(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT allocation_exclusion_reasons_tenant_exclusion_sequence_unique
        UNIQUE (tenant_id, exclusion_id, sequence_order)
);

-- =============================================================================
-- F. resource_gaps and alternatives
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.resource_gaps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    recommendation_id UUID NOT NULL,
    request_id UUID NOT NULL,
    requirement_id UUID,
    gap_type TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    gap_description TEXT NOT NULL,
    eligible_count INTEGER NOT NULL DEFAULT 0,
    excluded_count INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT resource_gaps_recommendation_fkey
        FOREIGN KEY (tenant_id, recommendation_id)
        REFERENCES public.allocation_recommendations(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT resource_gaps_request_fkey
        FOREIGN KEY (tenant_id, request_id)
        REFERENCES public.allocation_requests(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT resource_gaps_requirement_fkey
        FOREIGN KEY (tenant_id, requirement_id)
        REFERENCES public.allocation_requirements(tenant_id, id) ON DELETE SET NULL,
    CONSTRAINT resource_gaps_tenant_id_unique UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS public.resource_alternatives (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    gap_id UUID NOT NULL,
    recommendation_id UUID NOT NULL,
    sequence_order INTEGER NOT NULL,
    alternative_type TEXT NOT NULL,
    description TEXT NOT NULL,
    requires_approval BOOLEAN NOT NULL DEFAULT TRUE,
    estimated_effort_hours NUMERIC(18, 2),
    cost_impact NUMERIC(18, 2),
    CONSTRAINT resource_alternatives_sequence_positive CHECK (sequence_order >= 1),
    CONSTRAINT resource_alternatives_gap_fkey
        FOREIGN KEY (tenant_id, gap_id)
        REFERENCES public.resource_gaps(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT resource_alternatives_recommendation_fkey
        FOREIGN KEY (tenant_id, recommendation_id)
        REFERENCES public.allocation_recommendations(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT resource_alternatives_tenant_gap_sequence_unique
        UNIQUE (tenant_id, gap_id, sequence_order)
);

-- =============================================================================
-- G. budget_validation_results
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.budget_validation_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    recommendation_id UUID NOT NULL,
    request_id UUID NOT NULL,
    requirement_id UUID NOT NULL,
    resource_id UUID NOT NULL,
    sufficient_balance BOOLEAN NOT NULL,
    cost_centre_match BOOLEAN NOT NULL,
    currency_match BOOLEAN NOT NULL,
    validity_period_valid BOOLEAN NOT NULL,
    within_authorization_limit BOOLEAN NOT NULL,
    available_balance NUMERIC(18, 2) NOT NULL,
    required_amount NUMERIC(18, 2) NOT NULL,
    validation_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT budget_validation_results_balances_non_negative
        CHECK (available_balance >= 0 AND required_amount >= 0),
    CONSTRAINT budget_validation_results_recommendation_fkey
        FOREIGN KEY (tenant_id, recommendation_id)
        REFERENCES public.allocation_recommendations(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT budget_validation_results_request_fkey
        FOREIGN KEY (tenant_id, request_id)
        REFERENCES public.allocation_requests(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT budget_validation_results_requirement_fkey
        FOREIGN KEY (tenant_id, requirement_id)
        REFERENCES public.allocation_requirements(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT budget_validation_results_resource_fkey
        FOREIGN KEY (tenant_id, resource_id)
        REFERENCES public.resources(tenant_id, id),
    CONSTRAINT budget_validation_results_tenant_rec_req_unique
        UNIQUE (tenant_id, recommendation_id, requirement_id)
);

-- =============================================================================
-- H. recommendation_evidence_links
-- =============================================================================

ALTER TABLE public.evidence_references
    ADD CONSTRAINT evidence_references_tenant_id_unique UNIQUE (tenant_id, id);

CREATE TABLE IF NOT EXISTS public.recommendation_evidence_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    recommendation_id UUID NOT NULL,
    resource_id UUID,
    evidence_reference_id UUID,
    evidence_key TEXT NOT NULL,
    link_type TEXT NOT NULL,
    sequence_order INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT recommendation_evidence_links_sequence_positive
        CHECK (sequence_order >= 1),
    CONSTRAINT recommendation_evidence_links_recommendation_fkey
        FOREIGN KEY (tenant_id, recommendation_id)
        REFERENCES public.allocation_recommendations(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT recommendation_evidence_links_evidence_fkey
        FOREIGN KEY (tenant_id, evidence_reference_id)
        REFERENCES public.evidence_references(tenant_id, id) ON DELETE SET NULL,
    CONSTRAINT recommendation_evidence_links_tenant_rec_key_sequence_unique
        UNIQUE (tenant_id, recommendation_id, evidence_key, sequence_order)
);

-- =============================================================================
-- I. Indexes
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_allocation_requests_tenant_correlation
    ON public.allocation_requests (tenant_id, correlation_id);

CREATE INDEX IF NOT EXISTS idx_allocation_recommendations_tenant_correlation_version
    ON public.allocation_recommendations (tenant_id, correlation_id, recommendation_version DESC);

CREATE INDEX IF NOT EXISTS idx_allocation_recommendations_tenant_request
    ON public.allocation_recommendations (tenant_id, request_id);

CREATE INDEX IF NOT EXISTS idx_allocation_candidates_tenant_recommendation
    ON public.allocation_candidates (tenant_id, recommendation_id, candidate_rank);

CREATE INDEX IF NOT EXISTS idx_allocation_exclusions_tenant_recommendation
    ON public.allocation_exclusions (tenant_id, recommendation_id);

CREATE INDEX IF NOT EXISTS idx_resource_gaps_tenant_recommendation
    ON public.resource_gaps (tenant_id, recommendation_id);

CREATE INDEX IF NOT EXISTS idx_resource_alternatives_tenant_gap_sequence
    ON public.resource_alternatives (tenant_id, gap_id, sequence_order);

CREATE INDEX IF NOT EXISTS idx_budget_validation_results_tenant_recommendation
    ON public.budget_validation_results (tenant_id, recommendation_id);

CREATE INDEX IF NOT EXISTS idx_recommendation_evidence_links_tenant_recommendation
    ON public.recommendation_evidence_links (tenant_id, recommendation_id);

-- =============================================================================
-- J. RLS preparation (enable only — repository tenant filters mandatory)
-- =============================================================================

ALTER TABLE public.allocation_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.allocation_requirements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.allocation_recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.allocation_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.allocation_exclusions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.allocation_exclusion_reasons ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.resource_gaps ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.resource_alternatives ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.budget_validation_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recommendation_evidence_links ENABLE ROW LEVEL SECURITY;
