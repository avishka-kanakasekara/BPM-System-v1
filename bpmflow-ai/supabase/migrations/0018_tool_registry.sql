-- Phase 5: tenant-scoped DB Tool Registry (resolution only — no execution).
-- Does not seed demo rows. Does not store secrets.

CREATE TABLE IF NOT EXISTS public.tool_registry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id),
    tool_name TEXT NOT NULL,
    display_name TEXT,
    description TEXT,
    tool_category TEXT NOT NULL,
    action_code TEXT NOT NULL,
    implementation_key TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '1',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    requires_authorization BOOLEAN NOT NULL DEFAULT TRUE,
    allowed_step_types JSONB NOT NULL DEFAULT '[]'::jsonb,
    required_permissions JSONB NOT NULL DEFAULT '[]'::jsonb,
    input_schema JSONB NOT NULL DEFAULT '{"type":"object","properties":{}}'::jsonb,
    output_schema JSONB NOT NULL DEFAULT '{"type":"object","properties":{}}'::jsonb,
    configuration JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    CONSTRAINT tool_registry_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT tool_registry_tenant_name_version_unique UNIQUE (tenant_id, tool_name, version),
    CONSTRAINT tool_registry_category_check CHECK (
        tool_category IN (
            'COMMUNICATION',
            'APPROVAL',
            'PROCUREMENT',
            'TASK',
            'DOCUMENT',
            'VALIDATION',
            'SYSTEM',
            'RESOURCE',
            'NOTIFICATION'
        )
    ),
    CONSTRAINT tool_registry_action_check CHECK (
        action_code IN (
            'CREATE_TASK',
            'UPDATE_TASK',
            'SEND_EMAIL',
            'SEND_REMINDER',
            'CREATE_PURCHASE_ORDER',
            'REQUEST_QUOTATION',
            'UPDATE_PROCUREMENT_RECORD',
            'ESCALATE',
            'CREATE_EXCEPTION',
            'GET_PROCESS_HISTORY',
            'GET_TASK_HISTORY',
            'CALCULATE_KPI'
        )
    ),
    CONSTRAINT tool_registry_tool_name_check CHECK (char_length(btrim(tool_name)) > 0),
    CONSTRAINT tool_registry_implementation_key_check CHECK (char_length(btrim(implementation_key)) > 0),
    CONSTRAINT tool_registry_version_check CHECK (char_length(btrim(version)) > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS tool_registry_one_enabled_action
    ON public.tool_registry (tenant_id, action_code)
    WHERE enabled = TRUE;

CREATE INDEX IF NOT EXISTS idx_tool_registry_tenant_action_enabled
    ON public.tool_registry (tenant_id, action_code, enabled);

CREATE INDEX IF NOT EXISTS idx_tool_registry_tenant_category_enabled
    ON public.tool_registry (tenant_id, tool_category, enabled);

COMMENT ON TABLE public.tool_registry IS
    'Tenant-scoped tool definitions. Resolves WorkflowStep required_action to an allow-listed implementation. Does not execute tools or store secrets.';
COMMENT ON COLUMN public.tool_registry.implementation_key IS
    'Allow-listed implementation identifier (not a Python import path).';
COMMENT ON COLUMN public.tool_registry.requires_authorization IS
    'Whether Agent 4 authorization is required. Registration is not execution authorization.';
COMMENT ON COLUMN public.tool_registry.configuration IS
    'Non-secret operational metadata only.';

ALTER TABLE public.tool_registry ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tool_registry_service_role ON public.tool_registry;
CREATE POLICY tool_registry_service_role
    ON public.tool_registry FOR ALL TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS tool_registry_tenant_authenticated ON public.tool_registry;
CREATE POLICY tool_registry_tenant_authenticated
    ON public.tool_registry FOR SELECT TO authenticated
    USING (
        tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
    );
