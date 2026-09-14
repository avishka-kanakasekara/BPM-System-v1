import type { AppRole, WorkflowStepRecord } from '../../types/api'

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function formatProcessType(type: string | null | undefined): string {
  if (!type) return '—'
  return type
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

export function displayText(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return null
}

export function canGovern(role: AppRole | string | null | undefined): boolean {
  const key = (role || '').toLowerCase()
  return key === 'approver' || key === 'admin'
}

const TERMINAL_STEP = new Set([
  'COMPLETED',
  'FAILED',
  'SKIPPED',
  'CANCELLED',
  'EXCEPTION',
])

/** UX hint only. Backend still decides whether the step may run. */
export function isStepExecutableInUi(opts: {
  processStage: string
  planStatus?: string | null
  step: WorkflowStepRecord
}): boolean {
  if (opts.processStage !== 'WORKFLOW_EXECUTION') return false
  if ((opts.planStatus || '').toUpperCase() !== 'ACTIVE') return false
  const status = String(opts.step.status || '').toUpperCase()
  const type = String(opts.step.step_type || '').toUpperCase()
  if (TERMINAL_STEP.has(status)) return false
  if (status === 'WAITING_HUMAN_APPROVAL' || status === 'WAITING_DEPENDENCY') return false
  if (type === 'APPROVAL' && status !== 'COMPLETED') return false
  if (status === 'IN_PROGRESS') return false
  return status === 'PENDING' || status === 'READY' || status === 'AUTHORIZED'
}

export function factSourceLabel(source: string | null | undefined): string | null {
  if (!source) return null
  if (source === 'extracted_evidence' || source === 'authenticated' || source === 'company_repository' || source === 'policy_repository') {
    return 'Verified / evidence-backed'
  }
  if (source === 'agent_derived') return 'Agent-derived interpretation'
  if (source === 'unspecified') return null
  return source
}
