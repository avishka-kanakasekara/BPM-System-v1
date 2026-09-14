-- Phase 10: tenant-scoped TO-BE process recommendations.
-- Observational only. Acceptance does not activate a WorkflowPlan.

CREATE TABLE IF NOT EXISTS public.tobe_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id),
    process_id UUID REFERENCES public.processes(id) ON DELETE SET NULL,
    workflow_plan_id UUID,
    recommendation_type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    reason TEXT NOT NULL,
    evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    kpi_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    expected_benefit TEXT,
    risk TEXT,
    confidence NUMERIC(6, 4),
    status TEXT NOT NULL DEFAULT 'PROPOSED',
    fingerprint TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    reviewed_at TIMESTAMPTZ,
    reviewed_by UUID,
    CONSTRAINT tobe_recommendations_status_check CHECK (
        status IN ('PROPOSED', 'ACCEPTED', 'REJECTED', 'IMPLEMENTED', 'NOT_ALLOWED')
    ),
    CONSTRAINT tobe_recommendations_tenant_fingerprint_unique UNIQUE (tenant_id, fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_tobe_recommendations_tenant_process
    ON public.tobe_recommendations (tenant_id, process_id);
CREATE INDEX IF NOT EXISTS idx_tobe_recommendations_tenant_status
    ON public.tobe_recommendations (tenant_id, status);

COMMENT ON TABLE public.tobe_recommendations IS
    'Agent 4 observational TO-BE recommendations. Human review required; never auto-activates workflow.';

ALTER TABLE public.tobe_recommendations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tobe_recommendations_service_role ON public.tobe_recommendations;
DROP POLICY IF EXISTS tobe_recommendations_tenant_authenticated ON public.tobe_recommendations;

CREATE POLICY tobe_recommendations_service_role ON public.tobe_recommendations
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY tobe_recommendations_tenant_authenticated ON public.tobe_recommendations
    FOR SELECT TO authenticated
    USING (tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', ''));
