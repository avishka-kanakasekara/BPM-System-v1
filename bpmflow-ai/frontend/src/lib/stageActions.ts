import type { WorkflowStage } from '../types/api'

export type StageActionId =
  | 'autopilot'
  | 'approval'
  | 'invoice'
  | 'continue_autopilot'

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

/** Precondition-aware action enablement for the process cockpit. */
export function stageActions(ctx: StageActionContext): StageActionSpec[] {
  const { stage, hasDiscovery, hasTenant, busy, humanApprovalPending } = ctx
  const blocked = busy ? 'Another action is in progress' : undefined

  if (stage === 'DRAFT') {
    return [
      {
        id: 'autopilot',
        label: 'Run process autopilot',
        enabled: hasDiscovery && hasTenant && !busy,
        reason: !hasDiscovery
          ? 'Upload and analyze discovery evidence first'
          : !hasTenant
            ? 'Tenant context required — sign in again'
            : blocked,
      },
    ]
  }

  if (stage === 'DISCOVERING' || stage === 'RESOURCE_PLANNING' || stage === 'RISK_REVIEW') {
    return [
      {
        id: 'continue_autopilot',
        label: 'Continue autopilot',
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
    return [
      {
        id: 'continue_autopilot',
        label: 'Resume autopilot',
        enabled: hasTenant && !busy,
        reason: !hasTenant ? 'Tenant context required' : blocked,
      },
    ]
  }

  if (stage === 'INVOICE_MATCHING') {
    return [
      {
        id: 'invoice',
        label: 'Submit invoice match',
        enabled: !busy,
        reason: blocked,
      },
    ]
  }

  return []
}
