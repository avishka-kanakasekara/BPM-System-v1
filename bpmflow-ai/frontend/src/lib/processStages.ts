/**
 * Single source of truth for Agent 4 process stages.
 * Values match backend WorkflowStage (app/agents/agent4_orchestrator/constants.py).
 * Agent 4 owns current_stage. The UI must not imply unsupervised execution.
 */

export const WORKFLOW_STAGES = [
  'DRAFT',
  'DISCOVERING',
  'RESOURCE_PLANNING',
  'RISK_REVIEW',
  'AWAITING_HUMAN_APPROVAL',
  'WORKFLOW_EXECUTION',
  'INVOICE_MATCHING',
  'COMPLETED',
  'EXCEPTION',
] as const

export type WorkflowStage = (typeof WORKFLOW_STAGES)[number]

export const PROCESS_STAGE_LABELS: Record<WorkflowStage, string> = {
  DRAFT: 'Draft',
  DISCOVERING: 'Discovering',
  RESOURCE_PLANNING: 'Resource Planning',
  RISK_REVIEW: 'Risk Review',
  AWAITING_HUMAN_APPROVAL: 'Awaiting Human Approval',
  WORKFLOW_EXECUTION: 'Workflow Execution',
  INVOICE_MATCHING: 'Invoice Matching',
  COMPLETED: 'Completed',
  EXCEPTION: 'Exception',
}

/** Compact labels for the process cockpit timeline only. Values still come from WORKFLOW_STAGES. */
export const PROCESS_STAGE_TIMELINE_LABELS: Record<WorkflowStage, string> = {
  DRAFT: 'Draft',
  DISCOVERING: 'Discovering',
  RESOURCE_PLANNING: 'Resource Planning',
  RISK_REVIEW: 'Risk Review',
  AWAITING_HUMAN_APPROVAL: 'Human Approval',
  WORKFLOW_EXECUTION: 'Workflow Execution',
  INVOICE_MATCHING: 'Invoice Matching',
  COMPLETED: 'Completed',
  EXCEPTION: 'Exception',
}

/** Human-supervised descriptions — never “Agent 2 runs the whole workflow”. */
export const PROCESS_STAGE_DESCRIPTIONS: Record<WorkflowStage, string> = {
  DRAFT: 'Process exists. Upload discovery evidence. Nothing is approved or purchased yet.',
  DISCOVERING: 'Agent 1 extracted process facts from evidence. Review them; Agent 1 does not approve.',
  RESOURCE_PLANNING: 'Allocate eligible people and budget from the company directory (Agent 3). Recommendations are not approvals.',
  RISK_REVIEW: 'Agent 4 applies deterministic risk and policy rules. This does not authorize execution.',
  AWAITING_HUMAN_APPROVAL: 'A human approver must decide. Agents cannot skip this gate.',
  WORKFLOW_EXECUTION: 'Execute one authorized WorkflowStep at a time through the Tool Registry. Agent 2 does not run the full workflow automatically.',
  INVOICE_MATCHING: 'Match a persisted invoice against the purchase order. Caller-supplied expected totals are not the source of truth.',
  COMPLETED: 'Agent 4 completion gate passed. The process is finished.',
  EXCEPTION: 'The process is blocked. Authorized recovery may return to discovering. This is not completion.',
}

export const ACTIVE_PROCESS_STAGES: ReadonlySet<WorkflowStage> = new Set([
  'DISCOVERING',
  'RESOURCE_PLANNING',
  'RISK_REVIEW',
  'AWAITING_HUMAN_APPROVAL',
  'WORKFLOW_EXECUTION',
  'INVOICE_MATCHING',
])

export const PROCESS_JOURNEY_STAGES: WorkflowStage[] = [
  'DRAFT',
  'DISCOVERING',
  'RESOURCE_PLANNING',
  'RISK_REVIEW',
  'AWAITING_HUMAN_APPROVAL',
  'WORKFLOW_EXECUTION',
  'INVOICE_MATCHING',
  'COMPLETED',
]

export function isWorkflowStage(value: string | null | undefined): value is WorkflowStage {
  return Boolean(value && (WORKFLOW_STAGES as readonly string[]).includes(value))
}

export function formatProcessStage(stage: string | null | undefined): string {
  if (!stage) return 'Unknown'
  if (isWorkflowStage(stage)) return PROCESS_STAGE_LABELS[stage]
  return stage
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}
