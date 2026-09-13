-- Phase 8D: enrich public.exceptions for tenant-scoped process exceptions.
-- Reuses the existing exceptions table. Does not create a second exception store.

ALTER TABLE public.exceptions
    ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES public.tenants(id),
    ADD COLUMN IF NOT EXISTS workflow_plan_id UUID,
    ADD COLUMN IF NOT EXISTS workflow_step_id UUID,
    ADD COLUMN IF NOT EXISTS exception_code TEXT,
    ADD COLUMN IF NOT EXISTS title TEXT,
    ADD COLUMN IF NOT EXISTS source_agent TEXT,
    ADD COLUMN IF NOT EXISTS source_operation TEXT,
    ADD COLUMN IF NOT EXISTS evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS details JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS assigned_employee_id UUID,
    ADD COLUMN IF NOT EXISTS resolved_by_employee_id UUID,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW());

UPDATE public.exceptions AS e
SET tenant_id = p.tenant_id
FROM public.processes AS p
WHERE e.process_id = p.id
  AND e.tenant_id IS NULL
  AND p.tenant_id IS NOT NULL;

UPDATE public.exceptions
SET exception_code = type
WHERE exception_code IS NULL OR btrim(exception_code) = '';

UPDATE public.exceptions
SET title = left(description, 200)
WHERE title IS NULL OR btrim(title) = '';

CREATE INDEX IF NOT EXISTS idx_exceptions_tenant_process
    ON public.exceptions (tenant_id, process_id);
CREATE INDEX IF NOT EXISTS idx_exceptions_tenant_status
    ON public.exceptions (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_exceptions_tenant_step
    ON public.exceptions (tenant_id, workflow_step_id);
CREATE INDEX IF NOT EXISTS idx_exceptions_open_code
    ON public.exceptions (process_id, exception_code, status);

COMMENT ON TABLE public.exceptions IS
    'Authoritative BPM process exceptions. Agent 4 owns process EXCEPTION/COMPLETED; Agent 2 does not write current_stage.';
COMMENT ON COLUMN public.exceptions.exception_code IS
    'Controlled discrepancy/failure code (e.g. AMOUNT_MISMATCH). type remains the legacy severity-class column.';
COMMENT ON COLUMN public.exceptions.details IS
    'Structured evidence: invoice_id, purchase_order_id, discrepancy_codes, trace_id, execution_event_id.';

DROP POLICY IF EXISTS "Anyone can view exceptions" ON public.exceptions;
DROP POLICY IF EXISTS "anon_read_exceptions" ON public.exceptions;
DROP POLICY IF EXISTS "Exception assignees can update exceptions" ON public.exceptions;
DROP POLICY IF EXISTS exceptions_service_role ON public.exceptions;
DROP POLICY IF EXISTS exceptions_tenant_authenticated ON public.exceptions;

CREATE POLICY exceptions_service_role ON public.exceptions FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE POLICY exceptions_tenant_authenticated ON public.exceptions FOR SELECT TO authenticated
    USING (tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', ''));
