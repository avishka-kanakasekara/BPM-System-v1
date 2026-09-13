-- Agent 3 read-path persistence (Option A: shared resources catalog + extension tables)
-- Migration number 0002 — Agent 3 owned

-- =============================================================================
-- A. Tenant foundation
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW())
);

CREATE TRIGGER update_tenants_updated_at
    BEFORE UPDATE ON public.tenants
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Deterministic synthetic legacy tenant for existing demo resource rows (seed.sql)
INSERT INTO public.tenants (id, code, name, is_active)
VALUES (
    '00000000-0000-0000-0000-000000000099',
    'LEGACY_DEMO',
    'Synthetic Legacy Demo Tenant',
    TRUE
)
ON CONFLICT (code) DO NOTHING;

-- =============================================================================
-- B. Extend shared resources table (safe backfill)
-- =============================================================================

ALTER TABLE public.resources
    ADD COLUMN IF NOT EXISTS tenant_id UUID,
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS employee_identifier TEXT;

-- Backfill existing rows before enforcing NOT NULL
UPDATE public.resources
SET tenant_id = '00000000-0000-0000-0000-000000000099'
WHERE tenant_id IS NULL;

-- Normalize legacy lowercase type values to Agent 3 uppercase codes
UPDATE public.resources SET type = 'HUMAN' WHERE LOWER(type) = 'human';
UPDATE public.resources SET type = 'BUDGET' WHERE LOWER(type) = 'budget';
UPDATE public.resources SET type = 'EQUIPMENT' WHERE LOWER(type) = 'equipment';
UPDATE public.resources SET type = 'SYSTEM' WHERE LOWER(type) = 'software';

ALTER TABLE public.resources
    ALTER COLUMN tenant_id SET NOT NULL;

ALTER TABLE public.resources
    ADD CONSTRAINT resources_tenant_id_fkey
        FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);

ALTER TABLE public.resources
    ADD CONSTRAINT resources_tenant_id_id_unique UNIQUE (tenant_id, id);

ALTER TABLE public.resources
    ADD CONSTRAINT resources_type_check
        CHECK (type IN ('HUMAN', 'BUDGET', 'SYSTEM', 'EQUIPMENT', 'EXTERNAL_SERVICE'));

-- =============================================================================
-- C. Lookup tables
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    CONSTRAINT roles_tenant_code_unique UNIQUE (tenant_id, code),
    CONSTRAINT roles_tenant_id_unique UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS public.skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    CONSTRAINT skills_tenant_code_unique UNIQUE (tenant_id, code),
    CONSTRAINT skills_tenant_id_unique UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS public.authorities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    CONSTRAINT authorities_tenant_code_unique UNIQUE (tenant_id, code),
    CONSTRAINT authorities_tenant_id_unique UNIQUE (tenant_id, id)
);

-- =============================================================================
-- D. Junction tables
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.resource_roles (
    tenant_id UUID NOT NULL,
    resource_id UUID NOT NULL,
    role_id UUID NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (tenant_id, resource_id, role_id),
    CONSTRAINT resource_roles_resource_fkey
        FOREIGN KEY (tenant_id, resource_id)
        REFERENCES public.resources(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT resource_roles_role_fkey
        FOREIGN KEY (tenant_id, role_id)
        REFERENCES public.roles(tenant_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS public.resource_skills (
    tenant_id UUID NOT NULL,
    resource_id UUID NOT NULL,
    skill_id UUID NOT NULL,
    proficiency NUMERIC(5, 2),
    certified_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, resource_id, skill_id),
    CONSTRAINT resource_skills_proficiency_range
        CHECK (proficiency IS NULL OR (proficiency >= 0 AND proficiency <= 100)),
    CONSTRAINT resource_skills_resource_fkey
        FOREIGN KEY (tenant_id, resource_id)
        REFERENCES public.resources(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT resource_skills_skill_fkey
        FOREIGN KEY (tenant_id, skill_id)
        REFERENCES public.skills(tenant_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS public.resource_authorities (
    tenant_id UUID NOT NULL,
    resource_id UUID NOT NULL,
    authority_id UUID NOT NULL,
    granted_at TIMESTAMPTZ NOT NULL,
    valid_until TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, resource_id, authority_id),
    CONSTRAINT resource_authorities_resource_fkey
        FOREIGN KEY (tenant_id, resource_id)
        REFERENCES public.resources(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT resource_authorities_authority_fkey
        FOREIGN KEY (tenant_id, authority_id)
        REFERENCES public.authorities(tenant_id, id) ON DELETE CASCADE
);

-- =============================================================================
-- E. Profile extension tables
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.human_resource_profiles (
    tenant_id UUID NOT NULL,
    resource_id UUID NOT NULL,
    max_workload_pct NUMERIC(5, 2) NOT NULL,
    evidence_checked_at TIMESTAMPTZ NOT NULL,
    evidence_valid_until TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, resource_id),
    CONSTRAINT human_resource_profiles_workload_range
        CHECK (max_workload_pct >= 0 AND max_workload_pct <= 100),
    CONSTRAINT human_resource_profiles_evidence_window
        CHECK (evidence_valid_until >= evidence_checked_at),
    CONSTRAINT human_resource_profiles_resource_fkey
        FOREIGN KEY (tenant_id, resource_id)
        REFERENCES public.resources(tenant_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS public.budget_resource_profiles (
    tenant_id UUID NOT NULL,
    resource_id UUID NOT NULL,
    cost_centre TEXT NOT NULL,
    currency CHAR(3) NOT NULL,
    available_balance NUMERIC(18, 2) NOT NULL,
    authorization_limit NUMERIC(18, 2) NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_until TIMESTAMPTZ NOT NULL,
    evidence_checked_at TIMESTAMPTZ NOT NULL,
    evidence_valid_until TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, resource_id),
    CONSTRAINT budget_resource_profiles_balance_non_negative
        CHECK (available_balance >= 0 AND authorization_limit >= 0),
    CONSTRAINT budget_resource_profiles_validity_window
        CHECK (valid_until >= valid_from),
    CONSTRAINT budget_resource_profiles_evidence_window
        CHECK (evidence_valid_until >= evidence_checked_at),
    CONSTRAINT budget_resource_profiles_resource_fkey
        FOREIGN KEY (tenant_id, resource_id)
        REFERENCES public.resources(tenant_id, id) ON DELETE CASCADE
);

-- =============================================================================
-- F. Availability, workload, SoD, conflicts, evidence
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.resource_availability (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    resource_id UUID NOT NULL,
    available_from TIMESTAMPTZ NOT NULL,
    available_until TIMESTAMPTZ,
    reason TEXT,
    CONSTRAINT resource_availability_window
        CHECK (available_until IS NULL OR available_until >= available_from),
    CONSTRAINT resource_availability_resource_fkey
        FOREIGN KEY (tenant_id, resource_id)
        REFERENCES public.resources(tenant_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS public.workload_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    resource_id UUID NOT NULL,
    snapshot_at TIMESTAMPTZ NOT NULL,
    current_workload_pct NUMERIC(5, 2) NOT NULL,
    max_workload_pct NUMERIC(5, 2) NOT NULL,
    CONSTRAINT workload_snapshots_current_range
        CHECK (current_workload_pct >= 0 AND current_workload_pct <= 100),
    CONSTRAINT workload_snapshots_max_range
        CHECK (max_workload_pct >= 0 AND max_workload_pct <= 100),
    CONSTRAINT workload_snapshots_resource_fkey
        FOREIGN KEY (tenant_id, resource_id)
        REFERENCES public.resources(tenant_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS public.sod_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id),
    process_stage TEXT NOT NULL,
    first_role_code TEXT,
    first_action_code TEXT,
    conflicting_role_code TEXT,
    conflicting_action_code TEXT,
    reason TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT sod_rules_meaningful_pair CHECK (
        (first_role_code IS NOT NULL AND conflicting_role_code IS NOT NULL)
        OR (first_action_code IS NOT NULL AND conflicting_action_code IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS public.resource_declared_conflicts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    resource_id UUID NOT NULL,
    conflicting_resource_id UUID,
    conflict_flag_code TEXT,
    reason TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    valid_until TIMESTAMPTZ,
    CONSTRAINT resource_declared_conflicts_target CHECK (
        conflicting_resource_id IS NOT NULL OR conflict_flag_code IS NOT NULL
    ),
    CONSTRAINT resource_declared_conflicts_resource_fkey
        FOREIGN KEY (tenant_id, resource_id)
        REFERENCES public.resources(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT resource_declared_conflicts_conflicting_resource_fkey
        FOREIGN KEY (tenant_id, conflicting_resource_id)
        REFERENCES public.resources(tenant_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS public.evidence_references (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    resource_id UUID NOT NULL,
    evidence_key TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    checked_at TIMESTAMPTZ NOT NULL,
    valid_until TIMESTAMPTZ NOT NULL,
    CONSTRAINT evidence_references_window
        CHECK (valid_until >= checked_at),
    CONSTRAINT evidence_references_resource_fkey
        FOREIGN KEY (tenant_id, resource_id)
        REFERENCES public.resources(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT evidence_references_tenant_resource_key_unique
        UNIQUE (tenant_id, resource_id, evidence_key)
);

-- =============================================================================
-- G. Resource type integrity triggers
-- =============================================================================

CREATE OR REPLACE FUNCTION public.agent3_enforce_human_resource_profile_type()
RETURNS TRIGGER AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM public.resources r
        WHERE r.tenant_id = NEW.tenant_id
          AND r.id = NEW.resource_id
          AND r.type = 'HUMAN'
    ) THEN
        RAISE EXCEPTION 'human_resource_profiles requires a HUMAN resource';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER human_resource_profiles_type_guard
    BEFORE INSERT OR UPDATE ON public.human_resource_profiles
    FOR EACH ROW EXECUTE FUNCTION public.agent3_enforce_human_resource_profile_type();

CREATE OR REPLACE FUNCTION public.agent3_enforce_budget_resource_profile_type()
RETURNS TRIGGER AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM public.resources r
        WHERE r.tenant_id = NEW.tenant_id
          AND r.id = NEW.resource_id
          AND r.type = 'BUDGET'
    ) THEN
        RAISE EXCEPTION 'budget_resource_profiles requires a BUDGET resource';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER budget_resource_profiles_type_guard
    BEFORE INSERT OR UPDATE ON public.budget_resource_profiles
    FOR EACH ROW EXECUTE FUNCTION public.agent3_enforce_budget_resource_profile_type();

-- =============================================================================
-- H. Indexes (avoid duplicating UNIQUE constraint indexes)
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_resources_tenant_type_active
    ON public.resources (tenant_id, type, is_active);

CREATE INDEX IF NOT EXISTS idx_resource_roles_tenant_resource
    ON public.resource_roles (tenant_id, resource_id);

CREATE INDEX IF NOT EXISTS idx_resource_skills_tenant_resource
    ON public.resource_skills (tenant_id, resource_id);

CREATE INDEX IF NOT EXISTS idx_resource_authorities_tenant_resource
    ON public.resource_authorities (tenant_id, resource_id);

CREATE INDEX IF NOT EXISTS idx_resource_availability_tenant_resource_from
    ON public.resource_availability (tenant_id, resource_id, available_from);

CREATE INDEX IF NOT EXISTS idx_workload_snapshots_tenant_resource_snapshot
    ON public.workload_snapshots (tenant_id, resource_id, snapshot_at DESC);

CREATE INDEX IF NOT EXISTS idx_sod_rules_tenant_stage_active
    ON public.sod_rules (tenant_id, process_stage, is_active);

CREATE INDEX IF NOT EXISTS idx_resource_declared_conflicts_tenant_resource
    ON public.resource_declared_conflicts (tenant_id, resource_id);

-- evidence_references UNIQUE (tenant_id, resource_id, evidence_key) covers lookup index

-- =============================================================================
-- I. RLS preparation (enable only — no runtime tenant policies yet)
-- Repository tenant filters are mandatory until shared auth/security exists.
-- =============================================================================

ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.authorities ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.resource_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.resource_skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.resource_authorities ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.human_resource_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.budget_resource_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.resource_availability ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workload_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sod_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.resource_declared_conflicts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.evidence_references ENABLE ROW LEVEL SECURITY;

-- No USING(true) policies on Agent 3 tables: runtime isolation depends on
-- backend repository tenant_id filters and future JWT tenant context.
