-- Phase 1: canonical ProcessContext + identity mapping (no invented HR rows)

ALTER TABLE public.processes
    ADD COLUMN IF NOT EXISTS tenant_id UUID,
    ADD COLUMN IF NOT EXISTS process_context JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS designated_approver_id UUID;

CREATE INDEX IF NOT EXISTS idx_processes_tenant_id
    ON public.processes (tenant_id);

CREATE INDEX IF NOT EXISTS idx_processes_tenant_process
    ON public.processes (tenant_id, id);

COMMENT ON COLUMN public.processes.process_context IS
    'Canonical tenant-scoped ProcessContext JSON. Source of truth for amount, currency, budget, quotations, identities. Does not replace current_stage.';

-- Optional mapping: auth user_id ↔ company HUMAN resource. Empty until Phase 2.
CREATE TABLE IF NOT EXISTS public.identity_links (
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    employee_resource_id UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    PRIMARY KEY (tenant_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_identity_links_resource
    ON public.identity_links (employee_resource_id)
    WHERE employee_resource_id IS NOT NULL;

ALTER TABLE public.identity_links ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS identity_links_service_role ON public.identity_links;
CREATE POLICY identity_links_service_role
    ON public.identity_links
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS identity_links_tenant_authenticated ON public.identity_links;
CREATE POLICY identity_links_tenant_authenticated
    ON public.identity_links
    FOR ALL
    TO authenticated
    USING (
        tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
    )
    WITH CHECK (
        tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
    );

-- Restrictive tenant filter for processes that have tenant_id set.
-- Legacy rows with NULL tenant_id remain readable (does not weaken USING true SELECT).
DROP POLICY IF EXISTS processes_tenant_restrict ON public.processes;
CREATE POLICY processes_tenant_restrict
    ON public.processes
    AS RESTRICTIVE
    FOR ALL
    TO authenticated
    USING (
        tenant_id IS NULL
        OR tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
    )
    WITH CHECK (
        tenant_id IS NULL
        OR tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
    );
