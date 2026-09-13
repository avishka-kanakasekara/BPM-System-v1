-- Durable process advancement runs for Agent 4 autopilot (Phase 6)
-- Every autonomous stage chain is correlation-tracked and idempotent.

CREATE TABLE IF NOT EXISTS public.process_advancement_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    process_id UUID NOT NULL REFERENCES public.processes(id) ON DELETE CASCADE,
    correlation_id UUID NOT NULL,
    idempotency_key TEXT NOT NULL,
    tenant_id UUID,
    performed_by UUID,
    task_id UUID,
    from_stage TEXT NOT NULL,
    current_stage TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'RUNNING',
    steps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    result_json JSONB,
    error_code TEXT,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT process_advancement_runs_status_check
        CHECK (
            status IN (
                'RUNNING',
                'COMPLETED',
                'WAITING_HUMAN',
                'WAITING_INPUT',
                'FAILED'
            )
        )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_process_advancement_idempotency
    ON public.process_advancement_runs(process_id, idempotency_key);

CREATE INDEX IF NOT EXISTS idx_process_advancement_process
    ON public.process_advancement_runs(process_id);

CREATE INDEX IF NOT EXISTS idx_process_advancement_status
    ON public.process_advancement_runs(status, updated_at);

COMMENT ON TABLE public.process_advancement_runs IS
    'Agent 4 autopilot advancement runs — transactional, idempotent, resumable.';
