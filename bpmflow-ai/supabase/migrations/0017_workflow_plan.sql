-- Phase 4: Agent 4 owned WorkflowPlan + WorkflowStep (definition only, no execution).
-- Does not create a Tool Registry. Does not duplicate ProcessContext facts.

-- Allow composite tenant FKs from workflow_plans to processes.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'processes_tenant_id_unique'
    ) THEN
        ALTER TABLE public.processes
            ADD CONSTRAINT processes_tenant_id_unique UNIQUE (tenant_id, id);
    END IF;
END $$;

-- =============================================================================
-- workflow_plans
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.workflow_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id),
    process_id UUID NOT NULL REFERENCES public.processes(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT',
    created_by_agent TEXT NOT NULL DEFAULT 'agent4',
    source_process_context_schema_version TEXT,
    source_process_context_ref TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    CONSTRAINT workflow_plans_status_check CHECK (
        status IN (
            'DRAFT',
            'READY',
            'ACTIVE',
            'COMPLETED',
            'CANCELLED',
            'SUPERSEDED',
            'EXCEPTION'
        )
    ),
    CONSTRAINT workflow_plans_version_positive CHECK (version >= 1),
    CONSTRAINT workflow_plans_created_by_agent_check CHECK (created_by_agent = 'agent4'),
    CONSTRAINT workflow_plans_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT workflow_plans_tenant_process_version_unique UNIQUE (tenant_id, process_id, version),
    CONSTRAINT workflow_plans_process_tenant_fkey
        FOREIGN KEY (tenant_id, process_id)
        REFERENCES public.processes (tenant_id, id)
);

CREATE UNIQUE INDEX IF NOT EXISTS workflow_plans_one_active
    ON public.workflow_plans (tenant_id, process_id)
    WHERE status = 'ACTIVE';

CREATE INDEX IF NOT EXISTS idx_workflow_plans_tenant_process
    ON public.workflow_plans (tenant_id, process_id);

CREATE INDEX IF NOT EXISTS idx_workflow_plans_tenant_status
    ON public.workflow_plans (tenant_id, status);

COMMENT ON TABLE public.workflow_plans IS
    'Agent 4 executable workflow definition. ProcessContext remains canonical for business facts.';

-- =============================================================================
-- workflow_steps
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.workflow_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    workflow_plan_id UUID NOT NULL,
    step_key TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    step_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    responsible_employee_id UUID,
    responsible_resource_id UUID,
    responsible_role_id UUID,
    responsible_department_id UUID,
    assignment_unresolved BOOLEAN NOT NULL DEFAULT FALSE,
    unresolved_reason TEXT,
    required_action TEXT,
    required_tool_category TEXT,
    inputs JSONB NOT NULL DEFAULT '{}'::jsonb,
    expected_outputs JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    policy_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    risk_level TEXT,
    approval_required BOOLEAN NOT NULL DEFAULT FALSE,
    approval_type TEXT,
    recipient_employee_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    CONSTRAINT workflow_steps_step_type_check CHECK (
        step_type IN (
            'HUMAN_TASK',
            'APPROVAL',
            'SYSTEM_ACTION',
            'COMMUNICATION',
            'VALIDATION',
            'DOCUMENT_REVIEW',
            'RESOURCE_ALLOCATION',
            'EXCEPTION_HANDLING'
        )
    ),
    CONSTRAINT workflow_steps_status_check CHECK (
        status IN (
            'PENDING',
            'READY',
            'WAITING_DEPENDENCY',
            'WAITING_HUMAN_APPROVAL',
            'AUTHORIZED',
            'IN_PROGRESS',
            'COMPLETED',
            'FAILED',
            'SKIPPED',
            'CANCELLED',
            'EXCEPTION'
        )
    ),
    CONSTRAINT workflow_steps_sequence_positive CHECK (sequence >= 1),
    CONSTRAINT workflow_steps_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT workflow_steps_plan_key_unique UNIQUE (tenant_id, workflow_plan_id, step_key),
    CONSTRAINT workflow_steps_plan_sequence_unique UNIQUE (tenant_id, workflow_plan_id, sequence),
    CONSTRAINT workflow_steps_plan_tenant_fkey
        FOREIGN KEY (tenant_id, workflow_plan_id)
        REFERENCES public.workflow_plans (tenant_id, id)
        ON DELETE CASCADE,
    CONSTRAINT workflow_steps_employee_fkey
        FOREIGN KEY (tenant_id, responsible_employee_id)
        REFERENCES public.employees (tenant_id, id),
    CONSTRAINT workflow_steps_resource_fkey
        FOREIGN KEY (tenant_id, responsible_resource_id)
        REFERENCES public.resources (tenant_id, id),
    CONSTRAINT workflow_steps_role_fkey
        FOREIGN KEY (tenant_id, responsible_role_id)
        REFERENCES public.roles (tenant_id, id),
    CONSTRAINT workflow_steps_department_fkey
        FOREIGN KEY (tenant_id, responsible_department_id)
        REFERENCES public.departments (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS idx_workflow_steps_plan_sequence
    ON public.workflow_steps (tenant_id, workflow_plan_id, sequence);

COMMENT ON TABLE public.workflow_steps IS
    'Ordered executable step owned by Agent 4. Creating a step is not executing it.';
COMMENT ON COLUMN public.workflow_steps.required_tool_category IS
    'Declared tool category only. Tool Registry belongs to a later phase.';
COMMENT ON COLUMN public.workflow_steps.approval_required IS
    'Whether approval is required. Does not mean approval has occurred.';

-- =============================================================================
-- workflow_step_dependencies (stable step UUIDs, same plan/tenant only)
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.workflow_step_dependencies (
    tenant_id UUID NOT NULL,
    workflow_plan_id UUID NOT NULL,
    step_id UUID NOT NULL,
    depends_on_step_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    CONSTRAINT workflow_step_dependencies_pkey
        PRIMARY KEY (tenant_id, step_id, depends_on_step_id),
    CONSTRAINT workflow_step_dependencies_no_self CHECK (step_id <> depends_on_step_id),
    CONSTRAINT workflow_step_dependencies_plan_fkey
        FOREIGN KEY (tenant_id, workflow_plan_id)
        REFERENCES public.workflow_plans (tenant_id, id)
        ON DELETE CASCADE,
    CONSTRAINT workflow_step_dependencies_step_fkey
        FOREIGN KEY (tenant_id, step_id)
        REFERENCES public.workflow_steps (tenant_id, id)
        ON DELETE CASCADE,
    CONSTRAINT workflow_step_dependencies_depends_fkey
        FOREIGN KEY (tenant_id, depends_on_step_id)
        REFERENCES public.workflow_steps (tenant_id, id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_workflow_step_dependencies_plan
    ON public.workflow_step_dependencies (tenant_id, workflow_plan_id);

COMMENT ON TABLE public.workflow_step_dependencies IS
    'Same-plan step graph. No self-edges. Cycles rejected in application validation.';

-- =============================================================================
-- RLS — tenant scoped; service_role bypass. Do not use USING (true) for authenticated.
-- =============================================================================

ALTER TABLE public.workflow_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workflow_steps ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workflow_step_dependencies ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS workflow_plans_service_role ON public.workflow_plans;
CREATE POLICY workflow_plans_service_role
    ON public.workflow_plans FOR ALL TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS workflow_steps_service_role ON public.workflow_steps;
CREATE POLICY workflow_steps_service_role
    ON public.workflow_steps FOR ALL TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS workflow_step_dependencies_service_role ON public.workflow_step_dependencies;
CREATE POLICY workflow_step_dependencies_service_role
    ON public.workflow_step_dependencies FOR ALL TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS workflow_plans_tenant_authenticated ON public.workflow_plans;
CREATE POLICY workflow_plans_tenant_authenticated
    ON public.workflow_plans FOR ALL TO authenticated
    USING (
        tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
    )
    WITH CHECK (
        tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
    );

DROP POLICY IF EXISTS workflow_steps_tenant_authenticated ON public.workflow_steps;
CREATE POLICY workflow_steps_tenant_authenticated
    ON public.workflow_steps FOR ALL TO authenticated
    USING (
        tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
    )
    WITH CHECK (
        tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
    );

DROP POLICY IF EXISTS workflow_step_dependencies_tenant_authenticated ON public.workflow_step_dependencies;
CREATE POLICY workflow_step_dependencies_tenant_authenticated
    ON public.workflow_step_dependencies FOR ALL TO authenticated
    USING (
        tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
    )
    WITH CHECK (
        tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
    );
