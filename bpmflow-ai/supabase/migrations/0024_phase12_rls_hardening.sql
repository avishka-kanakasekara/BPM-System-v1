-- Phase 12: close overly permissive RLS from 0001/0002 without rewriting history.
-- Authenticated clients are restricted to JWT app_metadata.tenant_id.
-- service_role retains full access (backend uses the service role).

-- ---------------------------------------------------------------------------
-- processes: drop USING (true) SELECT policies; require tenant match
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "Anyone can view processes" ON public.processes;
DROP POLICY IF EXISTS "anon_read_processes" ON public.processes;
DROP POLICY IF EXISTS "Authenticated users can create processes" ON public.processes;
DROP POLICY IF EXISTS "Process owners can update processes" ON public.processes;
DROP POLICY IF EXISTS processes_tenant_restrict ON public.processes;
DROP POLICY IF EXISTS processes_service_role ON public.processes;
DROP POLICY IF EXISTS processes_tenant_authenticated ON public.processes;
DROP POLICY IF EXISTS processes_tenant_insert ON public.processes;
DROP POLICY IF EXISTS processes_tenant_update ON public.processes;

CREATE POLICY processes_service_role ON public.processes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY processes_tenant_authenticated ON public.processes
    FOR SELECT TO authenticated
    USING (
        tenant_id IS NOT NULL
        AND tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
    );

CREATE POLICY processes_tenant_insert ON public.processes
    FOR INSERT TO authenticated
    WITH CHECK (
        tenant_id IS NOT NULL
        AND tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
    );

CREATE POLICY processes_tenant_update ON public.processes
    FOR UPDATE TO authenticated
    USING (
        tenant_id IS NOT NULL
        AND tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
    )
    WITH CHECK (
        tenant_id IS NOT NULL
        AND tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
    );

-- ---------------------------------------------------------------------------
-- tasks / agent_messages: isolate via parent process tenant
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "Anyone can view tasks" ON public.tasks;
DROP POLICY IF EXISTS "anon_read_tasks" ON public.tasks;
DROP POLICY IF EXISTS "Authenticated users can create tasks" ON public.tasks;
DROP POLICY IF EXISTS "Task assignees can update tasks" ON public.tasks;
DROP POLICY IF EXISTS tasks_service_role ON public.tasks;
DROP POLICY IF EXISTS tasks_tenant_authenticated ON public.tasks;

ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;

CREATE POLICY tasks_service_role ON public.tasks
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY tasks_tenant_authenticated ON public.tasks
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.processes p
            WHERE p.id = tasks.process_id
              AND p.tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
        )
    );

DROP POLICY IF EXISTS "System can manage agent messages" ON public.agent_messages;
DROP POLICY IF EXISTS "anon_read_agent_messages" ON public.agent_messages;
DROP POLICY IF EXISTS agent_messages_service_role ON public.agent_messages;
DROP POLICY IF EXISTS agent_messages_tenant_authenticated ON public.agent_messages;

ALTER TABLE public.agent_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY agent_messages_service_role ON public.agent_messages
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY agent_messages_tenant_authenticated ON public.agent_messages
    FOR SELECT TO authenticated
    USING (
        process_id IS NOT NULL
        AND EXISTS (
            SELECT 1 FROM public.processes p
            WHERE p.id = agent_messages.process_id
              AND p.tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
        )
    );

-- ---------------------------------------------------------------------------
-- resources: keep admin manage; drop world-readable SELECT
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "Anyone can view resources" ON public.resources;
DROP POLICY IF EXISTS resources_service_role ON public.resources;
DROP POLICY IF EXISTS resources_tenant_authenticated ON public.resources;

ALTER TABLE public.resources ENABLE ROW LEVEL SECURITY;

CREATE POLICY resources_service_role ON public.resources
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'resources' AND column_name = 'tenant_id'
    ) THEN
        EXECUTE $policy$
            CREATE POLICY resources_tenant_authenticated ON public.resources
                FOR SELECT TO authenticated
                USING (
                    tenant_id IS NOT NULL
                    AND tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
                )
        $policy$;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- audit_logs: tenant column + drop world-readable SELECT
-- ---------------------------------------------------------------------------
ALTER TABLE public.audit_logs
    ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES public.tenants(id);

UPDATE public.audit_logs AS a
SET tenant_id = p.tenant_id
FROM public.processes AS p
WHERE a.entity_id = p.id
  AND a.tenant_id IS NULL
  AND p.tenant_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant_timestamp
    ON public.audit_logs (tenant_id, timestamp DESC);

DROP POLICY IF EXISTS "Anyone can view audit logs" ON public.audit_logs;
DROP POLICY IF EXISTS "System can create audit logs" ON public.audit_logs;
DROP POLICY IF EXISTS audit_logs_service_role ON public.audit_logs;
DROP POLICY IF EXISTS audit_logs_tenant_authenticated ON public.audit_logs;
DROP POLICY IF EXISTS audit_logs_insert_authenticated ON public.audit_logs;

CREATE POLICY audit_logs_service_role ON public.audit_logs
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY audit_logs_tenant_authenticated ON public.audit_logs
    FOR SELECT TO authenticated
    USING (
        tenant_id IS NOT NULL
        AND tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
    );

-- ---------------------------------------------------------------------------
-- exceptions: drop remaining anon-read policy from 0002
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "anon_read_exceptions" ON public.exceptions;

-- ---------------------------------------------------------------------------
-- approval_requests: enable RLS (table had none)
-- ---------------------------------------------------------------------------
ALTER TABLE public.approval_requests ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS approval_requests_service_role ON public.approval_requests;
DROP POLICY IF EXISTS approval_requests_tenant_authenticated ON public.approval_requests;

CREATE POLICY approval_requests_service_role ON public.approval_requests
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY approval_requests_tenant_authenticated ON public.approval_requests
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.processes p
            WHERE p.id = approval_requests.process_id
              AND p.tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
        )
    );

-- ---------------------------------------------------------------------------
-- execution_receipts / workflow_events: isolate via process tenant
-- ---------------------------------------------------------------------------
ALTER TABLE public.execution_receipts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS execution_receipts_service_role ON public.execution_receipts;
DROP POLICY IF EXISTS execution_receipts_tenant_authenticated ON public.execution_receipts;

CREATE POLICY execution_receipts_service_role ON public.execution_receipts
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY execution_receipts_tenant_authenticated ON public.execution_receipts
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.processes p
            WHERE p.id = execution_receipts.process_id
              AND p.tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
        )
    );

ALTER TABLE public.workflow_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workflow_events_service_role ON public.workflow_events;
DROP POLICY IF EXISTS workflow_events_tenant_authenticated ON public.workflow_events;

CREATE POLICY workflow_events_service_role ON public.workflow_events
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE POLICY workflow_events_tenant_authenticated ON public.workflow_events
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.processes p
            WHERE p.id = workflow_events.process_id
              AND p.tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
        )
    );

-- ---------------------------------------------------------------------------
-- discovered_documents: drop 0002 anon_read
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "anon_read_discovered_documents" ON public.discovered_documents;

COMMENT ON COLUMN public.audit_logs.tenant_id IS
    'Tenant scope for authenticated audit reads. Populated from the related process when available.';
