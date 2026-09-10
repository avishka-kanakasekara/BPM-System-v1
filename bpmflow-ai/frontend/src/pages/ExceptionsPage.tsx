import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  apiErrorMessage,
  listExceptions,
  listProcesses,
  type ExceptionRecord,
  type ProcessRecord,
} from '../services/apiClient'
import {
  Alert,
  EmptyState,
  ExceptionStatusBadge,
  PageHeader,
  Panel,
  RiskBadge,
} from '../components/ui/primitives'
import { formatExceptionStatus, formatRiskLevel } from '../lib/statusPresentation'

const STATUS_FILTERS: Array<{ value: string; label: string }> = [
  { value: '', label: 'All statuses' },
  { value: 'open', label: 'Open' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'ignored', label: 'Ignored' },
]

const SEVERITY_FILTERS: Array<{ value: string; label: string }> = [
  { value: '', label: 'All severities' },
  { value: 'LOW', label: 'Low' },
  { value: 'MEDIUM', label: 'Medium' },
  { value: 'HIGH', label: 'High' },
  { value: 'CRITICAL', label: 'Critical' },
]

function exceptionsErrorMessage(err: unknown): string {
  const status = (err as { response?: { status?: number } })?.response?.status
  if (status === 401) return 'Your session has expired. Please sign in again.'
  if (status === 403) return "You don't have permission to perform this action."
  if (status === 404) return 'This exception could not be found.'
  if (status === 409) return 'This action is not available for the current exception state.'
  if (status === 503) return 'The exception service is temporarily unavailable.'
  return apiErrorMessage(err)
}

function formatDateTime(value: string | null | undefined): string {
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

function formatExceptionType(type: string | null | undefined): string {
  if (!type) return 'Exception'
  return type
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function normalizeSeverity(value: string | null | undefined): string {
  return (value || '').toUpperCase()
}

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-slate-200/70 ${className}`} />
}

function SummaryChip({
  label,
  value,
  description,
}: {
  label: string
  value: number
  description: string
}) {
  return (
    <div className="rounded-xl border border-slate-200/90 bg-white px-4 py-3 shadow-[0_1px_2px_rgb(15_23_42_/_0.04)]">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums text-slate-900">{value}</p>
      <p className="mt-0.5 text-xs text-slate-500">{description}</p>
    </div>
  )
}

export default function ExceptionsPage() {
  const [rows, setRows] = useState<ExceptionRecord[]>([])
  const [processes, setProcesses] = useState<ProcessRecord[]>([])
  const [statusFilter, setStatusFilter] = useState('open')
  const [severityFilter, setSeverityFilter] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [exceptions, procs] = await Promise.all([
        listExceptions(),
        listProcesses().catch(() => [] as ProcessRecord[]),
      ])
      setRows(exceptions)
      setProcesses(procs)
    } catch (err) {
      setError(exceptionsErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const processNameById = useMemo(() => {
    const map = new Map<string, string>()
    for (const p of processes) map.set(p.id, p.name)
    return map
  }, [processes])

  const counts = useMemo(
    () => ({
      open: rows.filter((r) => r.status === 'open').length,
      in_progress: rows.filter((r) => r.status === 'in_progress').length,
      resolved: rows.filter((r) => r.status === 'resolved').length,
      ignored: rows.filter((r) => r.status === 'ignored').length,
    }),
    [rows],
  )

  const filtersActive = Boolean(
    search.trim() || statusFilter !== 'open' || severityFilter,
  )

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return rows
      .filter((r) => {
        if (statusFilter && r.status !== statusFilter) return false
        if (severityFilter && normalizeSeverity(r.severity) !== severityFilter) return false
        if (!q) return true
        const name = (r.process_id && processNameById.get(r.process_id)) || ''
        const hay = [
          r.process_id || '',
          r.type,
          r.description,
          r.assigned_to || '',
          name,
        ]
          .join(' ')
          .toLowerCase()
        return hay.includes(q)
      })
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
  }, [rows, statusFilter, severityFilter, search, processNameById])

  const attentionRows = useMemo(
    () => filtered.filter((r) => r.status === 'open' || r.status === 'in_progress'),
    [filtered],
  )
  const historyRows = useMemo(
    () => filtered.filter((r) => r.status === 'resolved' || r.status === 'ignored'),
    [filtered],
  )

  const showAttention =
    !statusFilter || statusFilter === 'open' || statusFilter === 'in_progress'
  const showHistory =
    !statusFilter || statusFilter === 'resolved' || statusFilter === 'ignored'

  function clearFilters() {
    setSearch('')
    setStatusFilter('open')
    setSeverityFilter('')
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Exceptions"
        description="Monitor process failures and manage recovery actions."
      />

      {error ? (
        <Alert tone="error">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span>{error}</span>
            <button type="button" className="btn btn-ghost btn-xs" onClick={() => void refresh()}>
              Retry
            </button>
          </div>
        </Alert>
      ) : null}

      <section aria-label="Exception summary" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {loading ? (
          <>
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
          </>
        ) : (
          <>
            <SummaryChip label="Open" value={counts.open} description="Needs attention" />
            <SummaryChip
              label="In Progress"
              value={counts.in_progress}
              description="Recovery underway"
            />
            <SummaryChip
              label="Resolved"
              value={counts.resolved}
              description="Successfully resolved"
            />
            <SummaryChip
              label="Ignored"
              value={counts.ignored}
              description="Closed without recovery"
            />
          </>
        )}
      </section>

      <Panel>
        <div className="mb-5 space-y-3">
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_minmax(0,1fr)]">
            <label className="block text-sm">
              <span className="sr-only">Search exceptions</span>
              <input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by process, type, description, or assignee"
                className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-slate-400"
              />
            </label>
            <label className="block text-sm">
              <span className="sr-only">Status</span>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-slate-400"
                aria-label="Filter by status"
              >
                {STATUS_FILTERS.map((s) => (
                  <option key={s.value || 'all'} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="sr-only">Severity</span>
              <select
                value={severityFilter}
                onChange={(e) => setSeverityFilter(e.target.value)}
                className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-slate-400"
                aria-label="Filter by severity"
              >
                {SEVERITY_FILTERS.map((s) => (
                  <option key={s.value || 'all'} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {filtersActive ? (
            <div className="flex justify-end">
              <button type="button" className="btn btn-ghost btn-xs" onClick={clearFilters}>
                Clear Filters
              </button>
            </div>
          ) : null}
        </div>

        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-28 w-full" />
            ))}
          </div>
        ) : (
          <div className="space-y-8">
            {showAttention ? (
              <section aria-labelledby="attention-heading">
                <div className="mb-3">
                  <h3 id="attention-heading" className="text-sm font-semibold text-slate-900">
                    Requires Attention
                  </h3>
                  <p className="text-xs text-slate-500">
                    Open and in-progress exceptions that may need recovery.
                  </p>
                </div>

                {attentionRows.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50/80 px-4 py-8 text-center">
                    <p className="text-sm font-medium text-slate-800">
                      No exceptions require attention.
                    </p>
                    <p className="mt-1 text-sm text-slate-500">
                      Your processes are currently running without reported exceptions.
                    </p>
                  </div>
                ) : (
                  <ul className="space-y-3">
                    {attentionRows.map((ex) => {
                      const name =
                        (ex.process_id && processNameById.get(ex.process_id)) || null
                      const high =
                        normalizeSeverity(ex.severity) === 'HIGH' ||
                        normalizeSeverity(ex.severity) === 'CRITICAL'
                      return (
                        <li
                          key={ex.id}
                          className={[
                            'rounded-xl border p-4 sm:p-5',
                            high
                              ? 'border-rose-200/70 bg-rose-50/25'
                              : 'border-slate-200 bg-slate-50/40',
                          ].join(' ')}
                        >
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="font-medium text-slate-900">
                                {formatExceptionType(ex.type)}
                              </p>
                              <div className="mt-2 flex flex-wrap items-center gap-2">
                                <RiskBadge level={ex.severity} />
                                <span className="text-xs text-slate-500">
                                  {formatRiskLevel(ex.severity)}
                                </span>
                                <ExceptionStatusBadge status={ex.status} />
                              </div>
                              <p className="mt-3 text-sm text-slate-600">
                                <span className="font-medium text-slate-700">Process: </span>
                                {name ||
                                  (ex.process_id
                                    ? `Process ${ex.process_id.slice(0, 8)}…`
                                    : '—')}
                              </p>
                              <p className="mt-1 text-sm text-slate-700">{ex.description}</p>
                              <p className="mt-2 text-xs text-slate-500">
                                Created {formatDateTime(ex.created_at)}
                                {ex.assigned_to
                                  ? ` · Assigned ${ex.assigned_to.slice(0, 8)}…`
                                  : ''}
                              </p>
                            </div>
                            <Link
                              to={`/exceptions/${ex.id}`}
                              className="btn btn-primary btn-sm shrink-0"
                            >
                              View
                            </Link>
                          </div>
                        </li>
                      )
                    })}
                  </ul>
                )}
              </section>
            ) : null}

            {showHistory ? (
              <section aria-labelledby="history-heading">
                <div className="mb-3">
                  <h3 id="history-heading" className="text-sm font-semibold text-slate-900">
                    Exception History
                  </h3>
                  <p className="text-xs text-slate-500">Resolved and ignored exceptions.</p>
                </div>

                {historyRows.length === 0 ? (
                  <EmptyState
                    title="No resolved exceptions yet."
                    body="Closed recovery actions will appear here."
                  />
                ) : (
                  <>
                    <div className="hidden overflow-x-auto md:block">
                      <table className="min-w-full text-left text-sm">
                        <thead>
                          <tr className="border-b border-slate-100 text-xs font-medium uppercase tracking-wide text-slate-500">
                            <th className="pb-3 pr-4 font-medium">Type</th>
                            <th className="pb-3 pr-4 font-medium">Process</th>
                            <th className="pb-3 pr-4 font-medium">Severity</th>
                            <th className="pb-3 pr-4 font-medium">Status</th>
                            <th className="pb-3 pr-4 font-medium">Created</th>
                            <th className="pb-3 font-medium">Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {historyRows.map((ex) => (
                            <tr key={ex.id} className="border-b border-slate-50 last:border-0">
                              <td className="py-3 pr-4 font-medium text-slate-900">
                                {formatExceptionType(ex.type)}
                              </td>
                              <td className="max-w-[12rem] truncate py-3 pr-4 text-slate-600">
                                {(ex.process_id && processNameById.get(ex.process_id)) ||
                                  (ex.process_id
                                    ? `${ex.process_id.slice(0, 8)}…`
                                    : '—')}
                              </td>
                              <td className="py-3 pr-4">
                                <RiskBadge level={ex.severity} />
                              </td>
                              <td className="py-3 pr-4">
                                <ExceptionStatusBadge status={ex.status} />
                                <span className="sr-only">
                                  {formatExceptionStatus(ex.status)}
                                </span>
                              </td>
                              <td className="whitespace-nowrap py-3 pr-4 text-slate-500">
                                {formatDateTime(ex.created_at)}
                              </td>
                              <td className="py-3">
                                <Link
                                  to={`/exceptions/${ex.id}`}
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

                    <ul className="space-y-3 md:hidden">
                      {historyRows.map((ex) => (
                        <li
                          key={ex.id}
                          className="rounded-xl border border-slate-200 bg-slate-50/40 p-4"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="font-medium text-slate-900">
                                {formatExceptionType(ex.type)}
                              </p>
                              <div className="mt-2 flex flex-wrap gap-2">
                                <RiskBadge level={ex.severity} />
                                <ExceptionStatusBadge status={ex.status} />
                              </div>
                            </div>
                            <Link to={`/exceptions/${ex.id}`} className="btn btn-ghost btn-xs">
                              View
                            </Link>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </section>
            ) : null}
          </div>
        )}
      </Panel>
    </div>
  )
}
