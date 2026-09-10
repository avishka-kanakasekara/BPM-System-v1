import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  apiErrorMessage,
  listApprovals,
  listProcesses,
  type ApprovalRecord,
  type ProcessRecord,
} from '../services/apiClient'
import {
  Alert,
  ApprovalStatusBadge,
  EmptyState,
  PageHeader,
  Panel,
  RiskBadge,
} from '../components/ui/primitives'
import { formatApprovalStatus, formatRiskLevel } from '../lib/statusPresentation'

const STATUS_FILTERS: Array<{ value: string; label: string }> = [
  { value: '', label: 'All' },
  { value: 'PENDING', label: 'Pending' },
  { value: 'APPROVED', label: 'Approved' },
  { value: 'REJECTED', label: 'Rejected' },
  { value: 'CANCELLED', label: 'Cancelled' },
]

function approvalsErrorMessage(err: unknown): string {
  const status = (err as { response?: { status?: number } })?.response?.status
  if (status === 401) return 'Your session has expired. Please sign in again.'
  if (status === 403) return "You don't have permission to make approval decisions."
  if (status === 404) return 'This approval request could not be found.'
  if (status === 409) return 'This approval request has already been decided.'
  if (status === 503) return 'The approval service is temporarily unavailable.'
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

export default function ApprovalsPage() {
  const [rows, setRows] = useState<ApprovalRecord[]>([])
  const [processes, setProcesses] = useState<ProcessRecord[]>([])
  const [statusFilter, setStatusFilter] = useState('PENDING')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [approvals, procs] = await Promise.all([
        listApprovals(),
        listProcesses().catch(() => [] as ProcessRecord[]),
      ])
      setRows(approvals)
      setProcesses(procs)
    } catch (err) {
      setError(approvalsErrorMessage(err))
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

  const counts = useMemo(() => {
    return {
      pending: rows.filter((r) => r.status === 'PENDING').length,
      approved: rows.filter((r) => r.status === 'APPROVED').length,
      rejected: rows.filter((r) => r.status === 'REJECTED').length,
    }
  }, [rows])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return rows
      .filter((r) => {
        if (statusFilter && r.status !== statusFilter) return false
        if (!q) return true
        const name = processNameById.get(r.process_id) || ''
        const hay = [r.process_id, r.reason, r.decision || '', r.comments || '', name]
          .join(' ')
          .toLowerCase()
        return hay.includes(q)
      })
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
  }, [rows, statusFilter, search, processNameById])

  const pendingRows = useMemo(
    () => filtered.filter((r) => r.status === 'PENDING'),
    [filtered],
  )
  const historyRows = useMemo(
    () => filtered.filter((r) => r.status !== 'PENDING'),
    [filtered],
  )

  const showPendingSection = !statusFilter || statusFilter === 'PENDING'
  const showHistorySection = !statusFilter || statusFilter !== 'PENDING'

  return (
    <div className="space-y-6">
      <PageHeader
        title="Approvals"
        description="Review AI-assisted risk decisions before business processes continue."
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

      <section aria-label="Approval summary" className="grid gap-3 sm:grid-cols-3">
        {loading ? (
          <>
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
          </>
        ) : (
          <>
            <SummaryChip
              label="Pending"
              value={counts.pending}
              description="Requires your decision"
            />
            <SummaryChip
              label="Approved"
              value={counts.approved}
              description="Previously authorized"
            />
            <SummaryChip
              label="Rejected"
              value={counts.rejected}
              description="Previously rejected"
            />
          </>
        )}
      </section>

      <Panel>
        <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center">
          <label className="block min-w-0 flex-1 text-sm">
            <span className="sr-only">Search approvals</span>
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by process, reason, or comments"
              className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-slate-400"
            />
          </label>
          <label className="block text-sm sm:w-48">
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
        </div>

        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-28 w-full" />
            ))}
          </div>
        ) : (
          <div className="space-y-8">
            {showPendingSection ? (
              <section aria-labelledby="pending-heading">
                <div className="mb-3 flex items-end justify-between gap-2">
                  <div>
                    <h3 id="pending-heading" className="text-sm font-semibold text-slate-900">
                      Requires Your Decision
                    </h3>
                    <p className="text-xs text-slate-500">
                      AI recommends. You decide whether the process may continue.
                    </p>
                  </div>
                  <span className="text-xs tabular-nums text-slate-500">
                    {pendingRows.length} pending
                  </span>
                </div>

                {pendingRows.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50/80 px-4 py-8 text-center">
                    <p className="text-sm font-medium text-slate-800">
                      No approvals require your attention.
                    </p>
                    <p className="mt-1 text-sm text-slate-500">You&apos;re all caught up.</p>
                  </div>
                ) : (
                  <ul className="space-y-3">
                    {pendingRows.map((a) => {
                      const name = processNameById.get(a.process_id)
                      return (
                        <li
                          key={a.id}
                          className="rounded-xl border border-amber-200/70 bg-amber-50/30 p-4 sm:p-5"
                        >
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="font-medium text-slate-900">
                                {name || `Process ${a.process_id.slice(0, 8)}…`}
                              </p>
                              <p className="mt-0.5 font-mono text-xs text-slate-500">{a.process_id}</p>
                              <div className="mt-3 flex flex-wrap items-center gap-2">
                                <RiskBadge level={a.risk_level} />
                                <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
                                  {formatRiskLevel(a.risk_level)} risk
                                </span>
                                <ApprovalStatusBadge status={a.status} />
                              </div>
                              <p className="mt-3 text-sm font-medium text-slate-800">
                                Human Approval Required
                              </p>
                              <p className="mt-1 text-sm text-slate-600">
                                <span className="font-medium text-slate-700">Reason: </span>
                                {a.reason}
                              </p>
                              <p className="mt-2 text-xs text-slate-500">
                                Requested {formatDateTime(a.created_at)}
                              </p>
                            </div>
                            <Link
                              to={`/approvals/${a.id}`}
                              className="btn btn-primary btn-sm shrink-0"
                            >
                              Review
                            </Link>
                          </div>
                        </li>
                      )
                    })}
                  </ul>
                )}
              </section>
            ) : null}

            {showHistorySection ? (
              <section aria-labelledby="history-heading">
                <div className="mb-3">
                  <h3 id="history-heading" className="text-sm font-semibold text-slate-900">
                    Decision History
                  </h3>
                  <p className="text-xs text-slate-500">Previous human authorization decisions.</p>
                </div>

                {historyRows.length === 0 ? (
                  <EmptyState
                    title="No approval decisions yet."
                    body="Approved and rejected requests will appear here."
                  />
                ) : (
                  <>
                    <div className="hidden overflow-x-auto md:block">
                      <table className="min-w-full text-left text-sm">
                        <thead>
                          <tr className="border-b border-slate-100 text-xs font-medium uppercase tracking-wide text-slate-500">
                            <th className="pb-3 pr-4 font-medium">Process</th>
                            <th className="pb-3 pr-4 font-medium">Risk</th>
                            <th className="pb-3 pr-4 font-medium">Decision</th>
                            <th className="pb-3 pr-4 font-medium">Approver</th>
                            <th className="pb-3 pr-4 font-medium">Date</th>
                            <th className="pb-3 pr-4 font-medium">Comments</th>
                            <th className="pb-3 font-medium">Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {historyRows.map((a) => (
                            <tr key={a.id} className="border-b border-slate-50 last:border-0">
                              <td className="max-w-[14rem] py-3 pr-4">
                                <p className="truncate font-medium text-slate-900">
                                  {processNameById.get(a.process_id) ||
                                    `Process ${a.process_id.slice(0, 8)}…`}
                                </p>
                              </td>
                              <td className="py-3 pr-4">
                                <RiskBadge level={a.risk_level} />
                              </td>
                              <td className="py-3 pr-4">
                                <ApprovalStatusBadge status={a.status} />
                                <span className="sr-only">{formatApprovalStatus(a.status)}</span>
                              </td>
                              <td className="py-3 pr-4 font-mono text-xs text-slate-600">
                                {a.approver_id ? `${a.approver_id.slice(0, 8)}…` : '—'}
                              </td>
                              <td className="whitespace-nowrap py-3 pr-4 text-slate-500">
                                {formatDateTime(a.decided_at || a.created_at)}
                              </td>
                              <td className="max-w-[12rem] truncate py-3 pr-4 text-slate-600">
                                {a.comments || '—'}
                              </td>
                              <td className="py-3">
                                <Link
                                  to={`/approvals/${a.id}`}
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
                      {historyRows.map((a) => (
                        <li
                          key={a.id}
                          className="rounded-xl border border-slate-200 bg-slate-50/40 p-4"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="truncate font-medium text-slate-900">
                                {processNameById.get(a.process_id) ||
                                  `Process ${a.process_id.slice(0, 8)}…`}
                              </p>
                              <div className="mt-2 flex flex-wrap gap-2">
                                <RiskBadge level={a.risk_level} />
                                <ApprovalStatusBadge status={a.status} />
                              </div>
                              <p className="mt-2 text-xs text-slate-500">
                                {formatDateTime(a.decided_at || a.created_at)}
                              </p>
                            </div>
                            <Link to={`/approvals/${a.id}`} className="btn btn-ghost btn-xs">
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
