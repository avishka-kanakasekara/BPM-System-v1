/**
 * Presentation helpers for BPM statuses.
 * API / domain values stay unchanged — only labels and visual tones change here.
 */

export type StatusTone = 'neutral' | 'good' | 'warn' | 'bad' | 'accent' | 'info'

const STAGE_LABELS: Record<string, string> = {
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

const RISK_LABELS: Record<string, string> = {
  LOW: 'Low',
  MEDIUM: 'Medium',
  HIGH: 'High',
  CRITICAL: 'Critical',
}

const APPROVAL_LABELS: Record<string, string> = {
  PENDING: 'Pending',
  APPROVED: 'Approved',
  REJECTED: 'Rejected',
  CANCELLED: 'Cancelled',
}

const EXCEPTION_LABELS: Record<string, string> = {
  open: 'Open',
  in_progress: 'In Progress',
  resolved: 'Resolved',
  ignored: 'Ignored',
}

function titleCaseFallback(value: string): string {
  return value
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export function formatProcessStage(stage: string | null | undefined): string {
  if (!stage) return 'Unknown'
  return STAGE_LABELS[stage] ?? titleCaseFallback(stage)
}

export function formatRiskLevel(level: string | null | undefined): string {
  if (!level) return 'Unknown'
  const key = level.toUpperCase()
  return RISK_LABELS[key] ?? titleCaseFallback(level)
}

export function formatApprovalStatus(status: string | null | undefined): string {
  if (!status) return 'Unknown'
  const key = status.toUpperCase()
  return APPROVAL_LABELS[key] ?? titleCaseFallback(status)
}

export function formatExceptionStatus(status: string | null | undefined): string {
  if (!status) return 'Unknown'
  const key = status.toLowerCase()
  return EXCEPTION_LABELS[key] ?? titleCaseFallback(status)
}

export function processStageTone(stage: string | null | undefined): StatusTone {
  switch (stage) {
    case 'COMPLETED':
      return 'good'
    case 'EXCEPTION':
      return 'bad'
    case 'AWAITING_HUMAN_APPROVAL':
    case 'RISK_REVIEW':
      return 'warn'
    case 'WORKFLOW_EXECUTION':
    case 'INVOICE_MATCHING':
    case 'DISCOVERING':
    case 'RESOURCE_PLANNING':
      return 'accent'
    case 'DRAFT':
    default:
      return 'neutral'
  }
}

export function riskTone(level: string | null | undefined): StatusTone {
  switch ((level || '').toUpperCase()) {
    case 'LOW':
      return 'good'
    case 'MEDIUM':
      return 'info'
    case 'HIGH':
      return 'warn'
    case 'CRITICAL':
      return 'bad'
    default:
      return 'neutral'
  }
}

export function approvalTone(status: string | null | undefined): StatusTone {
  switch ((status || '').toUpperCase()) {
    case 'PENDING':
      return 'warn'
    case 'APPROVED':
      return 'good'
    case 'REJECTED':
      return 'bad'
    case 'CANCELLED':
      return 'neutral'
    default:
      return 'neutral'
  }
}

export function exceptionTone(status: string | null | undefined): StatusTone {
  switch ((status || '').toLowerCase()) {
    case 'open':
      return 'bad'
    case 'in_progress':
      return 'warn'
    case 'resolved':
      return 'good'
    case 'ignored':
      return 'neutral'
    default:
      return 'neutral'
  }
}

export const STATUS_TONE_CLASSES: Record<StatusTone, string> = {
  neutral: 'bg-slate-100 text-slate-700 ring-1 ring-inset ring-slate-200/80',
  good: 'bg-emerald-50 text-emerald-800 ring-1 ring-inset ring-emerald-200/80',
  warn: 'bg-amber-50 text-amber-900 ring-1 ring-inset ring-amber-200/80',
  bad: 'bg-rose-50 text-rose-800 ring-1 ring-inset ring-rose-200/80',
  accent: 'bg-sky-50 text-sky-900 ring-1 ring-inset ring-sky-200/80',
  info: 'bg-slate-50 text-slate-700 ring-1 ring-inset ring-slate-200/80',
}
