-- Phase 1 schema hardening: missing FK indexes and idempotent constraints.

CREATE INDEX IF NOT EXISTS idx_processes_created_by ON public.processes(created_by);
CREATE INDEX IF NOT EXISTS idx_exceptions_process_id ON public.exceptions(process_id);
CREATE INDEX IF NOT EXISTS idx_agent_messages_task_id ON public.agent_messages(task_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_performed_by ON public.audit_logs(performed_by);
CREATE INDEX IF NOT EXISTS idx_approval_requests_task_id ON public.approval_requests(task_id);
CREATE INDEX IF NOT EXISTS idx_approval_requests_requested_by ON public.approval_requests(requested_by);

-- Ensure discovery audit table has an index on created_at for time-range queries.
CREATE INDEX IF NOT EXISTS idx_ingestion_audit_logs_created_at
    ON public.ingestion_audit_logs(created_at DESC);

-- Agent 1 discovery columns may pre-exist from 0002; enforce FK where safe.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'discovered_documents_process_id_fkey'
    ) THEN
        ALTER TABLE public.discovered_documents
            ADD CONSTRAINT discovered_documents_process_id_fkey
            FOREIGN KEY (process_id) REFERENCES public.processes(id) ON DELETE CASCADE;
    END IF;
END $$;
