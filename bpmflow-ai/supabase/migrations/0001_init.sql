-- Enable pgvector extension for vector embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- Users table (linked to Supabase auth)
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    role TEXT NOT NULL DEFAULT 'requester', -- requester, approver, admin
    department TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

-- Processes table
CREATE TABLE IF NOT EXISTS public.processes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    process_type TEXT NOT NULL, -- procurement, approval, etc.
    status TEXT NOT NULL DEFAULT 'draft', -- draft, active, archived
    version INTEGER DEFAULT 1,
    created_by UUID REFERENCES public.users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

-- Tasks table
CREATE TABLE IF NOT EXISTS public.tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    process_id UUID REFERENCES public.processes(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending', -- pending, in_progress, completed, failed
    assigned_to UUID REFERENCES public.users(id),
    priority TEXT DEFAULT 'medium', -- low, medium, high, urgent
    due_date TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

-- Resources table
CREATE TABLE IF NOT EXISTS public.resources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    type TEXT NOT NULL, -- human, equipment, software, budget
    capacity INTEGER,
    availability_percentage INTEGER DEFAULT 100,
    cost_per_hour DECIMAL(10,2),
    department TEXT,
    skills TEXT[], -- array of skills for human resources
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

-- Audit/Event log table
CREATE TABLE IF NOT EXISTS public.audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT NOT NULL, -- process, task, resource, user
    entity_id UUID NOT NULL,
    action TEXT NOT NULL, -- created, updated, deleted, assigned, completed
    performed_by UUID REFERENCES public.users(id),
    old_values JSONB,
    new_values JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

-- Exceptions/Issues table
CREATE TABLE IF NOT EXISTS public.exceptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID REFERENCES public.tasks(id) ON DELETE CASCADE,
    process_id UUID REFERENCES public.processes(id) ON DELETE CASCADE,
    severity TEXT NOT NULL, -- low, medium, high, critical
    type TEXT NOT NULL, -- timeout, resource_conflict, approval_denied, system_error
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open', -- open, in_progress, resolved, ignored
    assigned_to UUID REFERENCES public.users(id),
    resolution_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    resolved_at TIMESTAMP WITH TIME ZONE
);

-- Agent messages table for inter-agent communication
CREATE TABLE IF NOT EXISTS public.agent_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_agent TEXT NOT NULL, -- agent1, agent2, agent3, agent4
    to_agent TEXT NOT NULL,
    message_type TEXT NOT NULL, -- request, response, notification, alert
    content JSONB NOT NULL,
    process_id UUID REFERENCES public.processes(id),
    task_id UUID REFERENCES public.tasks(id),
    status TEXT NOT NULL DEFAULT 'sent', -- sent, delivered, processed, failed
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE
);

-- Document embeddings table for vector search
CREATE TABLE IF NOT EXISTS public.document_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536),
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_tasks_process_id ON public.tasks(process_id);
CREATE INDEX IF NOT EXISTS idx_tasks_assigned_to ON public.tasks(assigned_to);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON public.tasks(status);
CREATE INDEX IF NOT EXISTS idx_resources_type ON public.resources(type);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON public.audit_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_exceptions_task_id ON public.exceptions(task_id);
CREATE INDEX IF NOT EXISTS idx_exceptions_status ON public.exceptions(status);
CREATE INDEX IF NOT EXISTS idx_agent_messages_process_id ON public.agent_messages(process_id);
CREATE INDEX IF NOT EXISTS idx_agent_messages_status ON public.agent_messages(status);
CREATE INDEX IF NOT EXISTS idx_document_embeddings_document_id ON public.document_embeddings(document_id);

-- Create vector similarity search index
CREATE INDEX IF NOT EXISTS idx_document_embeddings_embedding ON public.document_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Row Level Security (RLS) policies
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.processes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.resources ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.exceptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_messages ENABLE ROW LEVEL SECURITY;

-- Basic RLS policies (you may want to customize these based on your security requirements)
CREATE POLICY "Users can view all users" ON public.users FOR SELECT USING (true);
CREATE POLICY "Users can update own profile" ON public.users FOR UPDATE USING (auth.uid() = id);

CREATE POLICY "Anyone can view processes" ON public.processes FOR SELECT USING (true);
CREATE POLICY "Authenticated users can create processes" ON public.processes FOR INSERT WITH CHECK (auth.uid() IS NOT NULL);
CREATE POLICY "Process owners can update processes" ON public.processes FOR UPDATE USING (created_by = auth.uid());

CREATE POLICY "Anyone can view tasks" ON public.tasks FOR SELECT USING (true);
CREATE POLICY "Authenticated users can create tasks" ON public.tasks FOR INSERT WITH CHECK (auth.uid() IS NOT NULL);
CREATE POLICY "Task assignees can update tasks" ON public.tasks FOR UPDATE USING (assigned_to = auth.uid());

CREATE POLICY "Anyone can view resources" ON public.resources FOR SELECT USING (true);
CREATE POLICY "Admins can manage resources" ON public.resources FOR ALL USING (EXISTS (SELECT 1 FROM public.users WHERE id = auth.uid() AND role = 'admin'));

CREATE POLICY "Anyone can view audit logs" ON public.audit_logs FOR SELECT USING (true);
CREATE POLICY "System can create audit logs" ON public.audit_logs FOR INSERT WITH CHECK (true);

CREATE POLICY "Anyone can view exceptions" ON public.exceptions FOR SELECT USING (true);
CREATE POLICY "Exception assignees can update exceptions" ON public.exceptions FOR UPDATE USING (assigned_to = auth.uid());

CREATE POLICY "System can manage agent messages" ON public.agent_messages FOR ALL USING (true);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = TIMEZONE('utc', NOW());
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers to automatically update updated_at
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON public.users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_processes_updated_at BEFORE UPDATE ON public.processes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_tasks_updated_at BEFORE UPDATE ON public.tasks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_resources_updated_at BEFORE UPDATE ON public.resources
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
