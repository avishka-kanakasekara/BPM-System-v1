-- Agent 1 discovery persistence on Supabase.
-- Safe to re-run. Does not require auth.users rows (created_by / assigned_to stay nullable).

CREATE TABLE IF NOT EXISTS public.processes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    process_type TEXT NOT NULL DEFAULT 'discovered',
    status TEXT NOT NULL DEFAULT 'draft',
    version INTEGER DEFAULT 1,
    created_by UUID,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

ALTER TABLE public.processes ADD COLUMN IF NOT EXISTS process_json JSONB DEFAULT '{}'::jsonb;
ALTER TABLE public.processes ADD COLUMN IF NOT EXISTS overall_confidence DOUBLE PRECISION;
ALTER TABLE public.processes ADD COLUMN IF NOT EXISTS discovery_status TEXT;
ALTER TABLE public.processes ADD COLUMN IF NOT EXISTS trace_id UUID;
ALTER TABLE public.processes ADD COLUMN IF NOT EXISTS message_id UUID;

CREATE TABLE IF NOT EXISTS public.tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    process_id UUID REFERENCES public.processes(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    assigned_to UUID,
    priority TEXT DEFAULT 'medium',
    due_date TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

ALTER TABLE public.tasks ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0;
ALTER TABLE public.tasks ADD COLUMN IF NOT EXISTS actor TEXT;
ALTER TABLE public.tasks ADD COLUMN IF NOT EXISTS system TEXT;
ALTER TABLE public.tasks ADD COLUMN IF NOT EXISTS avg_duration DOUBLE PRECISION;

CREATE TABLE IF NOT EXISTS public.exceptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID REFERENCES public.tasks(id) ON DELETE CASCADE,
    process_id UUID REFERENCES public.processes(id) ON DELETE CASCADE,
    severity TEXT NOT NULL DEFAULT 'medium',
    type TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    assigned_to UUID,
    resolution_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    resolved_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS public.agent_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_agent TEXT NOT NULL,
    to_agent TEXT NOT NULL DEFAULT 'human',
    message_type TEXT NOT NULL DEFAULT 'notification',
    content JSONB NOT NULL,
    process_id UUID REFERENCES public.processes(id),
    task_id UUID REFERENCES public.tasks(id),
    status TEXT NOT NULL DEFAULT 'sent',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS public.ingestion_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    file_id UUID,
    detail_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.discovered_documents (
    id UUID PRIMARY KEY,
    process_id UUID REFERENCES public.processes(id) ON DELETE CASCADE,
    original_filename TEXT,
    sanitized_filename TEXT,
    mime_type TEXT,
    size_bytes INTEGER,
    ingest_status TEXT,
    doc_type TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_process_id ON public.tasks(process_id);
CREATE INDEX IF NOT EXISTS idx_exceptions_process_id ON public.exceptions(process_id);
CREATE INDEX IF NOT EXISTS idx_agent_messages_process_id ON public.agent_messages(process_id);
CREATE INDEX IF NOT EXISTS idx_discovered_documents_process_id ON public.discovered_documents(process_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_audit_logs_file_id ON public.ingestion_audit_logs(file_id);

ALTER TABLE public.processes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.exceptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ingestion_audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.discovered_documents ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anon_read_processes" ON public.processes;
CREATE POLICY "anon_read_processes" ON public.processes FOR SELECT USING (true);

DROP POLICY IF EXISTS "anon_read_tasks" ON public.tasks;
CREATE POLICY "anon_read_tasks" ON public.tasks FOR SELECT USING (true);

DROP POLICY IF EXISTS "anon_read_exceptions" ON public.exceptions;
CREATE POLICY "anon_read_exceptions" ON public.exceptions FOR SELECT USING (true);

DROP POLICY IF EXISTS "anon_read_agent_messages" ON public.agent_messages;
CREATE POLICY "anon_read_agent_messages" ON public.agent_messages FOR SELECT USING (true);

DROP POLICY IF EXISTS "anon_read_discovered_documents" ON public.discovered_documents;
CREATE POLICY "anon_read_discovered_documents" ON public.discovered_documents FOR SELECT USING (true);
