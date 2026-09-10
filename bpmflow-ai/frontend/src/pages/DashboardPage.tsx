import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import {
  apiErrorMessage,
  listApprovals,
  listAuditLogs,
  listExceptions,
  listProcesses,
  type ApprovalRecord,
  type AuditLogRecord,
  type ExceptionRecord,
  type ProcessRecord,
} from '../services/apiClient'
import { useAuth } from '../auth/AuthContext'
import {
  Alert,
  EmptyState,
  PageHeader,
  Panel,
  ProcessStageBadge,
  RiskBadge,
} from '../components/ui/primitives'
import { formatProcessStage } from '../lib/statusPresentation'

const ACTIVE_STAGES = new Set([
  'DISCOVERING',
  'RESOURCE_PLANNING',
  'RISK_REVIEW',
  'AWAITING_HUMAN_APPROVAL',
  'WORKFLOW_EXECUTION',
  'INVOICE_MATCHING',
])

const PIPELINE_STAGES: Array<{ key: string; label: string }> = [
  { key: 'DISCOVERING', label: 'Discovering' },
  { key: 'RESOURCE_PLANNING', label: 'Resource Planning' },
  { key: 'RISK_REVIEW', label: 'Risk Review' },
  { key: 'AWAITING_HUMAN_APPROVAL', label: 'Awaiting Approval' },
  { key: 'WORKFLOW_EXECUTION', label: 'Workflow Execution' },
  { key: 'INVOICE_MATCHING', label: 'Invoice Matching' },
  { key: 'COMPLETED', label: 'Completed' },
  { key: 'EXCEPTION', label: 'Exceptions' },
]

function greetingForNow(): string {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}

function formatShortDate(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function formatRelativeTime(value: string | null | undefined): string {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  const diffMs = Date.now() - d.getTime()
  const minutes = Math.round(diffMs / 60000)
  if (minutes < 1) return 'Just now'
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'} ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.round(hours / 24)
  if (days < 7) return `${days} day${days === 1 ? '' : 's'} ago`
  return formatShortDate(value)
}

function formatProcessType(type: string | null | undefined): string {
  if (!type) return '—'
  return type
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatProcessStatus(status: string | null | undefined): string {
  if (!status) return '—'
  const key = status.toUpperCase()
  if (key === 'ACTIVE' || key === 'IN_PROGRESS' || key === 'RUNNING') return 'Active'
  if (key === 'COMPLETED' || key === 'COMPLETE') return 'Completed'
  if (key === 'DRAFT') return 'Draft'
  if (key === 'EXCEPTION' || key === 'FAILED') return 'Exception'
  if (key === 'CANCELLED' || key === 'CANCELED') return 'Cancelled'
  return formatProcessType(status)
}

function formatAuditAction(action: string): string {
  const normalized = action.trim()
  const map: Record<string, string> = {
    PROCESS_CREATED: 'Process created',
    CREATE_PROCESS: 'Process created',
    CREATED: 'Created',
    STAGE_UPDATED: 'Stage updated',
    RISK_REVIEW: 'Risk review completed',
    RISK_REVIEW_COMPLETED: 'Risk review completed',
    APPROVAL_REQUESTED: 'Approval requested',
    APPROVAL_CREATED: 'Approval requested',
    APPROVED: 'Approval granted',
    REJECTED: 'Approval rejected',
    EXCEPTION_OPENED: 'Exception opened',
    EXCEPTION_CREATED: 'Exception opened',
    EXECUTE: 'Workflow execution started',
    COMPLETED: 'Process completed',
  }
  if (map[normalized]) return map[normalized]
  if (map[normalized.toUpperCase()]) return map[normalized.toUpperCase()]
  return normalized
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function dashboardErrorMessage(err: unknown): string {
  const status = (err as { response?: { status?: number } })?.response?.status
  if (status === 401) return 'Your session has expired. Please sign in again.'
  if (status === 403) return "You don't have permission to view this information."
  if (status === 503) return 'The BPMFlow AI service is temporarily unavailable.'
  return apiErrorMessage(err)
}

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-slate-200/70 ${className}`} />
}

function SummaryCardSkeleton() {
  return (
    <div className="rounded-xl border border-slate-200/90 bg-white p-5 shadow-[0_1px_2px_rgb(15_23_42_/_0.04)]">
      <Skeleton className="h-8 w-8 rounded-lg" />
      <Skeleton className="mt-4 h-7 w-16" />
      <Skeleton className="mt-2 h-4 w-28" />
      <Skeleton className="mt-2 h-3 w-36" />
    </div>
  )
}

function SummaryCard({
  label,
  value,
  description,
  icon,
  to,
}: {
  label: string
  value: number
  description: string
  icon: ReactNode
  to: string
}) {
  return (
    <Link
      to={to}
      className="group rounded-xl border border-slate-200/90 bg-white p-5 shadow-[0_1px_2px_rgb(15_23_42_/_0.04)] transition-colors hover:border-slate-300"
    >
      <div className="flex items-start justify-between gap-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-slate-600">
          {icon}
        </span>
      </div>
      <p className="mt-4 text-2xl font-semibold tracking-tight text-slate-900 tabular-nums">
        {value}
      </p>
      <p className="mt-1 text-sm font-medium text-slate-800">{label}</p>
      <p className="mt-0.5 text-xs text-slate-500">{description}</p>
    </Link>
  )
}

const Icons = {
  processes: (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden>
      <path strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h10M4 18h7" />
    </svg>
  ),
  approvals: (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden>
      <path strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5 2a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  exceptions: (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden>
      <path strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
    </svg>
  ),
  completed: (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden>
      <path strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  ),
}

type AttentionItem = {
  id: string
  kind: 'approval' | 'exception' | 'process'
  title: string
  subtitle: string
  riskLevel?: string
  meta?: string
  href: string
  cta: string
}

export default function DashboardPage() {
  const { session, user } = useAuth()
  const [processes, setProcesses] = useState<ProcessRecord[]>([])
  const [approvals, setApprovals] = useState<ApprovalRecord[]>([])
  const [exceptions, setExceptions] = useState<ExceptionRecord[]>([])
  const [activity, setActivity] = useState<AuditLogRecord[]>([])
  const [activityAvailable, setActivityAvailable] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      if (!session) {
        setProcesses([])
        setApprovals([])
        setExceptions([])
        setActivity([])
        setActivityAvailable(true)
        return
      }

      const [procs, pendingApprovals, openExceptions] = await Promise.all([
        listProcesses(),
        listApprovals('PENDING'),
        listExceptions('open'),
      ])
      setProcesses(procs)
      setApprovals(pendingApprovals)
      setExceptions(openExceptions)

      try {
        const logs = await listAuditLogs({ limit: 12 })
        setActivity(logs)
        setActivityAvailable(true)
      } catch {
        setActivity([])
        setActivityAvailable(false)
      }
    } catch (err) {
      setError(dashboardErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [session])

  useEffect(() => {
    void load()
  }, [load])

  const activeCount = useMemo(
    () => processes.filter((p) => ACTIVE_STAGES.has(p.current_stage)).length,
    [processes],
  )
  const completedCount = useMemo(
    () => processes.filter((p) => p.current_stage === 'COMPLETED').length,
    [processes],
  )

  const recentProcesses = useMemo(() => {
    return [...processes]
      .sort((a, b) => new Date(b.updated_at || b.created_at).getTime() - new Date(a.updated_at || a.created_at).getTime())
      .slice(0, 8)
  }, [processes])

  const stageCounts = useMemo(() => {
    const counts: Record<string, number> = Object.fromEntries(PIPELINE_STAGES.map((s) => [s.key, 0]))
    for (const p of processes) {
      if (counts[p.current_stage] !== undefined) counts[p.current_stage] += 1
    }
    return counts
  }, [processes])

  const stageMax = useMemo(
    () => Math.max(1, ...PIPELINE_STAGES.map((s) => stageCounts[s.key] ?? 0)),
    [stageCounts],
  )

  const processNameById = useMemo(() => {
    const map = new Map<string, string>()
    for (const p of processes) map.set(p.id, p.name)
    return map
  }, [processes])

  const attentionItems = useMemo((): AttentionItem[] => {
    const items: AttentionItem[] = []

    for (const a of approvals) {
      items.push({
        id: `approval-${a.id}`,
        kind: 'approval',
        title: 'Human Approval Required',
        subtitle: processNameById.get(a.process_id) || a.reason || `Process ${a.process_id.slice(0, 8)}…`,
        riskLevel: a.risk_level,
        href: '/approvals',
        cta: 'Review',
      })
    }

    for (const ex of exceptions) {
      items.push({
        id: `exception-${ex.id}`,
        kind: 'exception',
        title: 'Exception',
        subtitle: ex.description || ex.type || 'Open exception',
        riskLevel: ex.severity,
        href: '/exceptions',
        cta: 'View Exception',
      })
    }

    for (const p of processes) {
      if (p.current_stage === 'AWAITING_HUMAN_APPROVAL') {
        const alreadyCovered = approvals.some((a) => a.process_id === p.id)
        if (!alreadyCovered) {
          items.push({
            id: `process-approval-${p.id}`,
            kind: 'process',
            title: 'Awaiting Human Approval',
            subtitle: p.name,
            meta: formatProcessStage(p.current_stage),
            href: `/processes/${p.id}`,
            cta: 'Open',
          })
        }
      }
      if (p.current_stage === 'EXCEPTION') {
        const alreadyCovered = exceptions.some((e) => e.process_id === p.id)
        if (!alreadyCovered) {
          items.push({
            id: `process-exception-${p.id}`,
            kind: 'process',
            title: 'Process Exception',
            subtitle: p.name,
            meta: 'Needs attention',
            href: `/processes/${p.id}`,
            cta: 'View',
          })
        }
      }
    }

    return items.slice(0, 8)
  }, [approvals, exceptions, processes, processNameById])

  const firstName =
    user?.full_name?.trim().split(/\s+/)[0] ||
    user?.email?.split('@')[0] ||
    null

  const subtitle = firstName
    ? `${greetingForNow()}, ${firstName}. Monitor your business processes and actions that need your attention.`
    : 'Monitor your business processes and actions that need your attention.'

  return (
    <div className="space-y-8">
      <PageHeader title="Dashboard" description={subtitle} />

      {error ? (
        <Alert tone="error">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>{error}</span>
            <button type="button" className="btn btn-ghost btn-xs" onClick={() => void load()}>
              Retry
            </button>
          </div>
        </Alert>
      ) : null}

      {!session ? (
        <Alert tone="info">
          Sign in to view processes, approvals, and exceptions for your workspace.{' '}
          <Link to="/sign-in" className="font-medium underline underline-offset-2">
            Sign in
          </Link>
        </Alert>
      ) : null}

      {/* Summary */}
      <section aria-label="Summary">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {loading ? (
            <>
              <SummaryCardSkeleton />
              <SummaryCardSkeleton />
              <SummaryCardSkeleton />
              <SummaryCardSkeleton />
            </>
          ) : (
            <>
              <SummaryCard
                label="Active Processes"
                value={session ? activeCount : 0}
                description="Currently in progress"
                icon={Icons.processes}
                to="/processes"
              />
              <SummaryCard
                label="Pending Approvals"
                value={session ? approvals.length : 0}
                description="Require your review"
                icon={Icons.approvals}
                to="/approvals"
              />
              <SummaryCard
                label="Open Exceptions"
                value={session ? exceptions.length : 0}
                description="Need attention"
                icon={Icons.exceptions}
                to="/exceptions"
              />
              <SummaryCard
                label="Completed Processes"
                value={session ? completedCount : 0}
                description="Successfully completed"
                icon={Icons.completed}
                to="/processes"
              />
            </>
          )}
        </div>
      </section>

      {/* Pipeline overview */}
      <Panel
        title="Process pipeline"
        actions={
          <span className="text-xs font-normal text-slate-500">Where processes stand today</span>
        }
      >
        {loading ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {PIPELINE_STAGES.map((s) => (
              <Skeleton key={s.key} className="h-14 w-full" />
            ))}
          </div>
        ) : !session || processes.length === 0 ? (
          <p className="text-sm text-slate-500">No process stage data yet.</p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {PIPELINE_STAGES.map((stage) => {
              const count = stageCounts[stage.key] ?? 0
              const width = `${Math.round((count / stageMax) * 100)}%`
              return (
                <div key={stage.key} className="rounded-lg border border-slate-100 bg-slate-50/60 px-3 py-2.5">
                  <div className="flex items-baseline justify-between gap-2">
                    <p className="truncate text-xs font-medium text-slate-600">{stage.label}</p>
                    <p className="text-sm font-semibold tabular-nums text-slate-900">{count}</p>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200/80">
                    <div
                      className="h-full rounded-full bg-slate-500/70 transition-all"
                      style={{ width: count === 0 ? '0%' : width }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </Panel>

      <div className="grid gap-6 lg:grid-cols-5">
        {/* Recent processes — primary */}
        <div className="space-y-6 lg:col-span-3">
          <Panel
            title="Recent Processes"
            actions={
              <Link to="/processes" className="text-sm font-medium text-slate-700 hover:text-slate-900">
                View all processes
              </Link>
            }
          >
            <p className="-mt-2 mb-4 text-sm text-slate-500">Latest business processes in your workspace.</p>

            {loading ? (
              <div className="space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-12 w-full" />
                ))}
              </div>
            ) : !session ? (
              <EmptyState
                title="Sign in required"
                body="Authenticate to load processes for your workspace."
              />
            ) : recentProcesses.length === 0 ? (
              <div className="space-y-4">
                <EmptyState
                  title="No processes yet."
                  body="Create your first business process to get started."
                />
                <div className="text-center">
                  <Link to="/processes" className="btn btn-primary btn-sm">
                    Create Process
                  </Link>
                </div>
              </div>
            ) : (
              <>
                {/* Desktop table */}
                <div className="hidden overflow-x-auto md:block">
                  <table className="min-w-full text-left text-sm">
                    <thead>
                      <tr className="border-b border-slate-100 text-xs font-medium uppercase tracking-wide text-slate-500">
                        <th className="pb-3 pr-4 font-medium">Process</th>
                        <th className="pb-3 pr-4 font-medium">Type</th>
                        <th className="pb-3 pr-4 font-medium">Status</th>
                        <th className="pb-3 pr-4 font-medium">Current Stage</th>
                        <th className="pb-3 pr-4 font-medium">Created</th>
                        <th className="pb-3 font-medium">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {recentProcesses.map((p) => (
                        <tr key={p.id} className="border-b border-slate-50 last:border-0">
                          <td className="py-3.5 pr-4">
                            <Link
                              to={`/processes/${p.id}`}
                              className="font-medium text-slate-900 hover:underline"
                            >
                              {p.name}
                            </Link>
                          </td>
                          <td className="py-3.5 pr-4 text-slate-600">{formatProcessType(p.process_type)}</td>
                          <td className="py-3.5 pr-4 text-slate-600">{formatProcessStatus(p.status)}</td>
                          <td className="py-3.5 pr-4">
                            <ProcessStageBadge stage={p.current_stage} />
                          </td>
                          <td className="py-3.5 pr-4 whitespace-nowrap text-slate-500">
                            {formatShortDate(p.created_at)}
                          </td>
                          <td className="py-3.5">
                            <Link
                              to={`/processes/${p.id}`}
                              className="text-sm font-medium text-slate-700 hover:text-slate-900"
                            >
                              View
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Mobile cards */}
                <div className="space-y-3 md:hidden">
                  {recentProcesses.map((p) => (
                    <Link
                      key={p.id}
                      to={`/processes/${p.id}`}
                      className="block rounded-lg border border-slate-200 bg-slate-50/50 p-4"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate font-medium text-slate-900">{p.name}</p>
                          <p className="mt-0.5 text-xs text-slate-500">
                            {formatProcessType(p.process_type)} · {formatShortDate(p.created_at)}
                          </p>
                        </div>
                        <span className="shrink-0 text-sm font-medium text-slate-600">View</span>
                      </div>
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        <span className="text-xs text-slate-500">{formatProcessStatus(p.status)}</span>
                        <ProcessStageBadge stage={p.current_stage} />
                      </div>
                    </Link>
                  ))}
                </div>
              </>
            )}
          </Panel>
        </div>

        {/* Attention + Activity */}
        <div className="space-y-6 lg:col-span-2">
          <Panel title="Requires Your Attention">
            {loading ? (
              <div className="space-y-3">
                <Skeleton className="h-20 w-full" />
                <Skeleton className="h-20 w-full" />
              </div>
            ) : !session ? (
              <p className="text-sm text-slate-500">Sign in to see items that need your attention.</p>
            ) : attentionItems.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50/80 px-4 py-8 text-center">
                <p className="text-sm font-medium text-slate-800">You&apos;re all caught up.</p>
                <p className="mt-1 text-sm text-slate-500">Nothing currently requires your attention.</p>
              </div>
            ) : (
              <ul className="space-y-3">
                {attentionItems.map((item) => (
                  <li
                    key={item.id}
                    className="rounded-lg border border-slate-200/90 bg-slate-50/40 px-4 py-3"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-slate-900">{item.title}</p>
                        <p className="mt-0.5 truncate text-sm text-slate-600">{item.subtitle}</p>
                        {item.riskLevel || item.meta ? (
                          <div className="mt-2 flex flex-wrap items-center gap-2">
                            {item.riskLevel ? <RiskBadge level={item.riskLevel} /> : null}
                            {item.meta ? <span className="text-xs text-slate-500">{item.meta}</span> : null}
                          </div>
                        ) : null}
                      </div>
                      <Link
                        to={item.href}
                        className="btn btn-ghost btn-xs shrink-0 font-medium text-slate-700"
                      >
                        {item.cta}
                      </Link>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel title="Recent Activity">
            {loading ? (
              <div className="space-y-3">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : !session ? (
              <p className="text-sm text-slate-500">Sign in to view recent activity.</p>
            ) : !activityAvailable ? (
              <p className="text-sm text-slate-500">No recent activity available.</p>
            ) : activity.length === 0 ? (
              <p className="text-sm text-slate-500">No recent activity.</p>
            ) : (
              <ul className="space-y-0 divide-y divide-slate-100">
                {activity.slice(0, 8).map((log) => {
                  const entityLabel =
                    (log.entity_type === 'process' && processNameById.get(log.entity_id)) ||
                    `${log.entity_type} ${log.entity_id.slice(0, 8)}…`
                  return (
                    <li key={log.id} className="flex items-start justify-between gap-3 py-3 first:pt-0 last:pb-0">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-slate-800">{formatAuditAction(log.action)}</p>
                        <p className="mt-0.5 truncate text-xs text-slate-500">{entityLabel}</p>
                      </div>
                      <time className="shrink-0 text-xs text-slate-400" dateTime={log.timestamp}>
                        {formatRelativeTime(log.timestamp)}
                      </time>
                    </li>
                  )
                })}
              </ul>
            )}
          </Panel>
        </div>
      </div>
    </div>
  )
}
