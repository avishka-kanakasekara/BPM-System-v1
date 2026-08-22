-- Agent 4 workflow orchestration support
-- Adds BPM workflow stage tracking and human approval requests

-- Add Agent 4 workflow stage to processes without changing record status semantics
ALTER TABLE public.processes
    ADD COLUMN IF NOT EXISTS current_stage TEXT NOT NULL DEFAULT 'DRAFT';

ALTER TABLE public.processes
    DROP CONSTRAINT IF EXISTS processes_current_stage_check;

ALTER TABLE public.processes
    ADD CONSTRAINT processes_current_stage_check
    CHECK (
        current_stage IN (
            'DRAFT',
            'DISCOVERING',
            'RESOURCE_PLANNING',
            'RISK_REVIEW',
            'AWAITING_HUMAN_APPROVAL',
            'WORKFLOW_EXECUTION',
            'INVOICE_MATCHING',
            'EXCEPTION',
            'COMPLETED'
        )
    );

COMMENT ON COLUMN public.processes.current_stage IS
    'Agent 4 BPM workflow stage for orchestration and state transitions; separate from processes.status record lifecycle.';

-- Approval requests table for Agent 4 human approval gates
CREATE TABLE IF NOT EXISTS public.approval_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    process_id UUID NOT NULL REFERENCES public.processes(id) ON DELETE CASCADE,
    task_id UUID REFERENCES public.tasks(id) ON DELETE SET NULL,
    requested_by UUID REFERENCES public.users(id) ON DELETE SET NULL,
    approver_id UUID REFERENCES public.users(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    risk_level TEXT NOT NULL,
    reason TEXT NOT NULL,
    decision TEXT,
    comments TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    decided_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT approval_requests_status_check
        CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED')),
    CONSTRAINT approval_requests_risk_level_check
        CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    CONSTRAINT approval_requests_decision_check
        CHECK (decision IS NULL OR decision IN ('APPROVED', 'REJECTED')),
    CONSTRAINT approval_requests_decided_at_check
        CHECK (
            (status = 'PENDING' AND decision IS NULL)
            OR (status IN ('APPROVED', 'REJECTED') AND decision = status AND decided_at IS NOT NULL)
            OR (status = 'CANCELLED' AND decision IS NULL)
        )
);

COMMENT ON TABLE public.approval_requests IS
    'Agent 4 human approval gate requests for process and task decisions, including risk-based routing and final outcomes.';

COMMENT ON COLUMN public.approval_requests.process_id IS
    'Process that requires a human approval decision.';

COMMENT ON COLUMN public.approval_requests.task_id IS
    'Optional related task requiring approval within the process.';

COMMENT ON COLUMN public.approval_requests.requested_by IS
    'User who initiated the approval request, if applicable.';

COMMENT ON COLUMN public.approval_requests.approver_id IS
    'Assigned approver responsible for reviewing the request.';

COMMENT ON COLUMN public.approval_requests.status IS
    'Approval request lifecycle status managed by Agent 4 and human approvers.';

COMMENT ON COLUMN public.approval_requests.risk_level IS
    'Risk severity used by Agent 4 to route and prioritize approval decisions.';

COMMENT ON COLUMN public.approval_requests.reason IS
    'Why the approval gate was raised.';

COMMENT ON COLUMN public.approval_requests.decision IS
    'Final approval outcome when a decision has been made.';

COMMENT ON COLUMN public.approval_requests.comments IS
    'Optional approver comments or justification.';

COMMENT ON COLUMN public.approval_requests.created_at IS
    'Timestamp when the approval request was created.';

COMMENT ON COLUMN public.approval_requests.decided_at IS
    'Timestamp when the approval request was approved or rejected.';

-- Indexes for Agent 4 workflow and approval query patterns
CREATE INDEX IF NOT EXISTS idx_processes_current_stage ON public.processes(current_stage);
CREATE INDEX IF NOT EXISTS idx_approval_requests_process_id ON public.approval_requests(process_id);
CREATE INDEX IF NOT EXISTS idx_approval_requests_approver_id ON public.approval_requests(approver_id);
CREATE INDEX IF NOT EXISTS idx_approval_requests_status ON public.approval_requests(status);
