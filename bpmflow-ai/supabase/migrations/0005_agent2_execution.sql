-- 0005_agent2_execution.sql
-- Integrates Agent 2 (Workflow Execution / RPA) into the shared data layer.
--
-- Table ownership after this migration:
--   processes       — canonical process record. Owners: Agent 1 (discovery
--                     fields), Agent 4 (current_stage — sole writer via
--                     StateMachine), Agent 2 (execution_status + metadata_json
--                     + requester/priority columns added here). Replaces
--                     Agent 2's former private process_instances table.
--   tasks           — canonical task record. Owners: Agent 1 (workflow steps),
--                     Agent 2 (execution fields added here). Agent 2 writes
--                     assigned_to_email (TEXT); the pre-existing assigned_to
--                     UUID column remains reserved for user FK assignment.
--   agent_messages  — canonical message transport row. Agent 2's envelope
--                     fields (message_uid/trace_id/evidence_refs/confidence)
--                     are added as optional columns; sender/receiver/task_type
--                     map onto from_agent/to_agent/message_type.
--   audit_logs      — canonical audit trail. Agent 2's tool-guard decision
--                     fields (actor/agent/allowed/reason/payload) are added as
--                     optional columns; entity_id becomes nullable because a
--                     tool-guard decision may not reference a single entity.
--   All other Agent 2 tables (execution_plans .. optimization_recommendations)
--   are owned exclusively by Agent 2 and created here with FKs to the
--   canonical processes/tasks tables.

-- ---------------------------------------------------------------------------
-- Additive columns on shared tables
-- ---------------------------------------------------------------------------

ALTER TABLE public.processes
    ADD COLUMN IF NOT EXISTS priority TEXT,
    ADD COLUMN IF NOT EXISTS department TEXT,
    ADD COLUMN IF NOT EXISTS requester_email TEXT,
    ADD COLUMN IF NOT EXISTS execution_status TEXT,
    ADD COLUMN IF NOT EXISTS metadata_json JSONB;

ALTER TABLE public.tasks
    ADD COLUMN IF NOT EXISTS task_type TEXT,
    ADD COLUMN IF NOT EXISTS assigned_role TEXT,
    ADD COLUMN IF NOT EXISTS assigned_to_email TEXT,
    ADD COLUMN IF NOT EXISTS sla_hours DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS result_json JSONB,
    ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS sequence_order INTEGER;

ALTER TABLE public.agent_messages
    ADD COLUMN IF NOT EXISTS message_uid TEXT,
    ADD COLUMN IF NOT EXISTS trace_id TEXT,
    ADD COLUMN IF NOT EXISTS evidence_refs JSONB,
    ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION;

CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_messages_message_uid
    ON public.agent_messages(message_uid)
    WHERE message_uid IS NOT NULL;

ALTER TABLE public.audit_logs
    ADD COLUMN IF NOT EXISTS actor TEXT,
    ADD COLUMN IF NOT EXISTS agent TEXT,
    ADD COLUMN IF NOT EXISTS allowed BOOLEAN,
    ADD COLUMN IF NOT EXISTS reason TEXT,
    ADD COLUMN IF NOT EXISTS payload JSONB;

ALTER TABLE public.audit_logs
    ALTER COLUMN entity_id DROP NOT NULL;

-- ---------------------------------------------------------------------------
-- Agent 2 owned tables
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.execution_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    process_instance_id UUID NOT NULL REFERENCES public.processes(id) ON DELETE CASCADE,
    plan_version INTEGER DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'DRAFT',
    plan_json JSONB,
    reasoning TEXT,
    approved_by TEXT,
    approved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.execution_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES public.tasks(id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'RUNNING',
    started_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()),
    completed_at TIMESTAMP WITH TIME ZONE,
    result_json JSONB,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.tool_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_attempt_id UUID NOT NULL REFERENCES public.execution_attempts(id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    action TEXT NOT NULL,
    parameters_json JSONB,
    status TEXT NOT NULL DEFAULT 'PENDING',
    result_json JSONB,
    error_message TEXT,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    latency_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.execution_receipts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    process_id UUID NOT NULL REFERENCES public.processes(id) ON DELETE CASCADE,
    task_id UUID NOT NULL REFERENCES public.tasks(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    action TEXT NOT NULL,
    attempt_number INTEGER NOT NULL DEFAULT 1,
    idempotency_key TEXT NOT NULL UNIQUE,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()),
    completed_at TIMESTAMP WITH TIME ZONE,
    status TEXT NOT NULL DEFAULT 'RUNNING',
    result JSONB,
    error_type TEXT,
    error_message TEXT,
    latency_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.workflow_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    process_id UUID NOT NULL REFERENCES public.processes(id) ON DELETE CASCADE,
    task_id UUID REFERENCES public.tasks(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    actor TEXT,
    agent TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    metadata_json JSONB,
    previous_state TEXT,
    new_state TEXT
);

CREATE TABLE IF NOT EXISTS public.email_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_receipt_id UUID NOT NULL REFERENCES public.execution_receipts(id) ON DELETE CASCADE,
    recipient_email TEXT NOT NULL,
    recipient_role TEXT NOT NULL,
    subject TEXT NOT NULL,
    template_name TEXT,
    status TEXT NOT NULL DEFAULT 'QUEUED',
    sent_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.failures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_receipt_id UUID REFERENCES public.execution_receipts(id) ON DELETE SET NULL,
    task_id UUID REFERENCES public.tasks(id) ON DELETE SET NULL,
    failure_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'MEDIUM',
    description TEXT NOT NULL,
    root_cause TEXT,
    resolution_status TEXT NOT NULL DEFAULT 'OPEN',
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.retry_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    failure_id UUID NOT NULL REFERENCES public.failures(id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL,
    strategy TEXT NOT NULL DEFAULT 'EXPONENTIAL_BACKOFF',
    status TEXT NOT NULL DEFAULT 'PENDING',
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    result_json JSONB,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.sla_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES public.tasks(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    sla_hours DOUBLE PRECISION NOT NULL,
    elapsed_hours DOUBLE PRECISION NOT NULL,
    threshold_percent DOUBLE PRECISION,
    notified_roles JSONB,
    message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.process_kpis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    process_instance_id UUID REFERENCES public.processes(id) ON DELETE CASCADE,
    process_type TEXT NOT NULL,
    time_window_start TIMESTAMP WITH TIME ZONE NOT NULL,
    time_window_end TIMESTAMP WITH TIME ZONE NOT NULL,
    avg_cycle_time_hours DOUBLE PRECISION,
    avg_task_duration_hours DOUBLE PRECISION,
    completion_rate DOUBLE PRECISION,
    sla_compliance_rate DOUBLE PRECISION,
    failure_rate DOUBLE PRECISION,
    throughput INTEGER,
    bottleneck_task TEXT,
    kpi_data_json JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.optimization_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    process_id UUID NOT NULL REFERENCES public.processes(id) ON DELETE CASCADE,
    recommendation_type TEXT NOT NULL,
    problem TEXT NOT NULL,
    root_cause TEXT NOT NULL,
    evidence JSONB,
    baseline_metric DOUBLE PRECISION,
    predicted_metric DOUBLE PRECISION,
    improvement_percent DOUBLE PRECISION,
    confidence DOUBLE PRECISION,
    risk TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING_APPROVAL',
    approved_by TEXT,
    approved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_execution_plans_process ON public.execution_plans(process_instance_id);
CREATE INDEX IF NOT EXISTS idx_execution_attempts_task ON public.execution_attempts(task_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_attempt ON public.tool_calls(execution_attempt_id);
CREATE INDEX IF NOT EXISTS idx_execution_receipts_process ON public.execution_receipts(process_id);
CREATE INDEX IF NOT EXISTS idx_execution_receipts_task ON public.execution_receipts(task_id);
CREATE INDEX IF NOT EXISTS idx_workflow_events_process ON public.workflow_events(process_id);
CREATE INDEX IF NOT EXISTS idx_email_events_receipt ON public.email_events(execution_receipt_id);
CREATE INDEX IF NOT EXISTS idx_failures_task ON public.failures(task_id);
CREATE INDEX IF NOT EXISTS idx_retry_attempts_failure ON public.retry_attempts(failure_id);
CREATE INDEX IF NOT EXISTS idx_sla_events_task ON public.sla_events(task_id);
CREATE INDEX IF NOT EXISTS idx_process_kpis_process ON public.process_kpis(process_instance_id);
CREATE INDEX IF NOT EXISTS idx_optimization_recommendations_process ON public.optimization_recommendations(process_id);
