-- 0009_agent2_scheduler_claiming.sql
-- Job claiming/locking columns for Agent 2 background scheduler.

ALTER TABLE public.scheduled_jobs
    ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS claimed_by TEXT,
    ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMP WITH TIME ZONE;

CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_claimed ON public.scheduled_jobs(claimed_at);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_next_attempt ON public.scheduled_jobs(next_attempt_at);
