-- Company Policy & Knowledge Repository (Agent 4 governance support)
-- Tenant-isolated policy documents, versions, chunks, and structured rules.

CREATE TABLE IF NOT EXISTS public.company_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    created_by UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    CONSTRAINT company_policies_category_check
        CHECK (
            category IN (
                'PROCUREMENT',
                'APPROVAL',
                'BUDGET',
                'AUTHORIZATION',
                'SLA',
                'SECURITY',
                'FINANCE',
                'GENERAL'
            )
        )
);

CREATE TABLE IF NOT EXISTS public.policy_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_id UUID NOT NULL REFERENCES public.company_policies(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,
    version_label TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT',
    document_name TEXT NOT NULL,
    document_type TEXT NOT NULL,
    source_document_id UUID,
    storage_path TEXT,
    effective_from TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    effective_to TIMESTAMP WITH TIME ZONE,
    uploaded_by UUID,
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    access_scope TEXT NOT NULL DEFAULT 'tenant',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT policy_versions_status_check
        CHECK (status IN ('DRAFT', 'ACTIVE', 'ARCHIVED')),
    CONSTRAINT policy_versions_unique_label
        UNIQUE (policy_id, version_label)
);

CREATE TABLE IF NOT EXISTS public.policy_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_version_id UUID NOT NULL REFERENCES public.policy_versions(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,
    chunk_index INTEGER NOT NULL,
    page_number INTEGER,
    section_title TEXT,
    text_content TEXT NOT NULL,
    embedding JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.policy_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_version_id UUID NOT NULL REFERENCES public.policy_versions(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,
    rule_type TEXT NOT NULL,
    operator TEXT,
    threshold_value NUMERIC,
    currency TEXT,
    required_approval TEXT,
    required_roles JSONB NOT NULL DEFAULT '[]'::jsonb,
    required_evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    sla_hours NUMERIC,
    description TEXT,
    source_chunk_id UUID REFERENCES public.policy_chunks(id) ON DELETE SET NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    CONSTRAINT policy_rules_type_check
        CHECK (
            rule_type IN (
                'HIGH_VALUE_THRESHOLD',
                'APPROVAL_THRESHOLD',
                'BUDGET_LIMIT',
                'REQUIRED_EVIDENCE',
                'REQUIRED_AUTHORIZATION',
                'SEGREGATION_OF_DUTIES',
                'SLA'
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_company_policies_tenant ON public.company_policies(tenant_id);
CREATE INDEX IF NOT EXISTS idx_company_policies_tenant_category ON public.company_policies(tenant_id, category);
CREATE INDEX IF NOT EXISTS idx_policy_versions_tenant_status ON public.policy_versions(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_policy_versions_policy ON public.policy_versions(policy_id);
CREATE INDEX IF NOT EXISTS idx_policy_chunks_version ON public.policy_chunks(policy_version_id);
CREATE INDEX IF NOT EXISTS idx_policy_chunks_tenant ON public.policy_chunks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_policy_rules_version ON public.policy_rules(policy_version_id);
CREATE INDEX IF NOT EXISTS idx_policy_rules_tenant_type ON public.policy_rules(tenant_id, rule_type);

-- At most one ACTIVE version per policy identity
CREATE UNIQUE INDEX IF NOT EXISTS uq_policy_versions_one_active
    ON public.policy_versions(policy_id)
    WHERE status = 'ACTIVE';

ALTER TABLE public.company_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.policy_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.policy_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.policy_rules ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.company_policies IS
    'Tenant-owned company policy identities for Agent 4 governance.';
COMMENT ON TABLE public.policy_versions IS
    'Versioned policy documents; only ACTIVE versions are used by default retrieval.';
COMMENT ON TABLE public.policy_chunks IS
    'Searchable evidence chunks from policy documents for retrieval and audit.';
COMMENT ON TABLE public.policy_rules IS
    'Structured deterministic rules extracted or supplied for Agent 4 risk comparison.';
