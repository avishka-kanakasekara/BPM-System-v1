import type { WorkflowStage } from './processStages'

export type StageActionId =
  | 'start_discovery_stage'
  | 'plan_resources'
  | 'run_risk_review'
  | 'approval'
  | 'match_persisted_invoice'

export type StageActionSpec = {
  id: StageActionId
  label: string
  enabled: boolean
  reason?: string
}

type StageActionContext = {
  stage: WorkflowStage
  hasDiscovery: boolean
  hasTenant: boolean
  busy: boolean
  humanApprovalPending: boolean
}

/** Explicit BPM actions. Not an unsupervised pipeline. */
export function stageActions(ctx: StageActionContext): StageActionSpec[] {
  const { stage, hasDiscovery, hasTenant, busy, humanApprovalPending } = ctx
  const blocked = busy ? 'Another action is in progress' : undefined

  if (stage === 'DRAFT') {
    return [
      {
        id: 'start_discovery_stage',
        label: 'Start discovery stage',
        enabled: hasDiscovery && hasTenant && !busy,
        reason: !hasDiscovery
          ? 'Upload and analyze discovery evidence first'
          : !hasTenant
            ? 'Tenant context required — sign in again'
            : blocked,
      },
    ]
  }

  if (stage === 'DISCOVERING' || stage === 'RESOURCE_PLANNING') {
    return [
      {
        id: 'plan_resources',
        label: 'Plan resources from directory',
        enabled: hasTenant && !busy,
        reason: !hasTenant ? 'Tenant context required' : blocked,
      },
    ]
  }

  if (stage === 'RISK_REVIEW') {
    return [
      {
        id: 'run_risk_review',
        label: 'Run risk review',
        enabled: hasTenant && !busy,
        reason: !hasTenant ? 'Tenant context required' : blocked,
      },
    ]
  }

  if (stage === 'AWAITING_HUMAN_APPROVAL' || humanApprovalPending) {
    return [
      {
        id: 'approval',
        label: 'Review approval',
        enabled: !busy,
        reason: blocked,
      },
    ]
  }

  if (stage === 'WORKFLOW_EXECUTION') {
    return []
  }

  if (stage === 'INVOICE_MATCHING') {
    return [
      {
        id: 'match_persisted_invoice',
        label: 'Match persisted invoice',
        enabled: !busy,
        reason: blocked,
      },
    ]
  }

  return []
}
