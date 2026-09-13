import type { AdvancementAction, AuditLogRecord, ExecutionReceipt } from '../types/api'

export type CorrelationTimelineEvent = {
  id: string
  timestamp: string
  title: string
  detail?: string
  correlationId?: string
  source: 'audit' | 'advancement' | 'receipt'
}

function formatAuditTitle(action: string): string {
  const map: Record<string, string> = {
    PROCESS_CREATED: 'Process created',
    CREATED: 'Process created',
    STAGE_UPDATED: 'Stage updated',
    START: 'Discovery started',
    PLAN_RESOURCES: 'Resources planned',
    RISK_REVIEW: 'Risk assessed',
    APPROVAL_REQUESTED: 'Approval requested',
    APPROVED: 'Approved by human',
    REJECTED: 'Approval rejected',
    EXECUTE: 'Execution started',
    COMPLETED: 'Process completed',
    EXCEPTION_OPENED: 'Process stopped',
  }
  const key = action.toUpperCase()
  if (map[key]) return map[key]
  return action
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

/** Merge audit logs, autonomous advancement actions, and receipts into one timeline. */
export function buildCorrelationTimeline(input: {
  audit: AuditLogRecord[]
  autonomousActions: AdvancementAction[]
  receipts: ExecutionReceipt[]
  correlationId?: string | null
}): CorrelationTimelineEvent[] {
  const events: CorrelationTimelineEvent[] = []

  for (const log of input.audit) {
    events.push({
      id: `audit-${log.id}`,
      timestamp: log.timestamp,
      title: formatAuditTitle(log.action),
      detail: log.performed_by ? `By ${log.performed_by}` : undefined,
      source: 'audit',
    })
  }

  for (const [idx, action] of input.autonomousActions.entries()) {
    events.push({
      id: `adv-${action.correlation_id}-${idx}`,
      timestamp: action.timestamp,
      title: action.action,
      detail: `${action.stage} · ${action.guardrail}`,
      correlationId: action.correlation_id,
      source: 'advancement',
    })
  }

  for (const receipt of input.receipts) {
    events.push({
      id: `receipt-${receipt.id}`,
      timestamp: receipt.created_at,
      title: `${receipt.tool_name} · ${receipt.action}`,
      detail: receipt.status,
      correlationId: input.correlationId || undefined,
      source: 'receipt',
    })
  }

  return events.sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
  )
}
