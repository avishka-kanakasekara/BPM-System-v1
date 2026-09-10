import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  apiErrorMessage,
  listProcesses,
  type ProcessRecord,
} from '../services/apiClient'
import {
  Alert,
  EmptyState,
  PageHeader,
  Panel,
  ProcessStageBadge,
} from '../components/ui/primitives'

const STAGE_FILTERS: Array<{ value: string; label: string }> = [
  { value: '', label: 'All stages' },
  { value: 'DRAFT', label: 'Draft' },
  { value: 'DISCOVERING', label: 'Discovering' },
  { value: 'RESOURCE_PLANNING', label: 'Resource Planning' },
  { value: 'RISK_REVIEW', label: 'Risk Review' },
  { value: 'AWAITING_HUMAN_APPROVAL', label: 'Awaiting Human Approval' },
  { value: 'WORKFLOW_EXECUTION', label: 'Workflow Execution' },
  { value: 'INVOICE_MATCHING', label: 'Invoice Matching' },
  { value: 'COMPLETED', label: 'Completed' },
  { value: 'EXCEPTION', label: 'Exception' },
]

const KNOWN_TYPES = ['PROCUREMENT', 'INVOICE', 'GENERAL'] as const

type SortKey = 'updated' | 'created' | 'name'

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

function processesErrorMessage(err: unknown): string {
  const status = (err as { response?: { status?: number } })?.response?.status
  if (status === 401) return 'Your session has expired. Please sign in again.'
  if (status === 403) return "You don't have permission to view processes."
  if (status === 503) return 'The BPMFlow AI service is temporarily unavailable.'
  return apiErrorMessage(err)
}

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-slate-200/70 ${className}`} />
}

function selectClassName() {
  return 'h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none focus:border-slate-400'
}

export default function ProcessesPage() {
  const [processes, setProcesses] = useState<ProcessRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [stageFilter, setStageFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('updated')

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const rows = await listProcesses()
      setProcesses(rows)
    } catch (err) {
      setError(processesErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const statusOptions = useMemo(() => {
    const fromData = new Set<string>()
    for (const p of processes) {
      if (p.status) fromData.add(p.status)
    }
    for (const known of ['ACTIVE', 'DRAFT', 'COMPLETED', 'EXCEPTION']) {
      fromData.add(known)
    }
    return Array.from(fromData).sort()
  }, [processes])

  const typeOptions = useMemo(() => {
    const fromData = new Set<string>(KNOWN_TYPES)
    for (const p of processes) {
      if (p.process_type) fromData.add(p.process_type)
    }
    return Array.from(fromData).sort()
  }, [processes])

  const filtersActive = Boolean(search.trim() || statusFilter || stageFilter || typeFilter || sortKey !== 'updated')

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    let rows = processes.filter((p) => {
      if (statusFilter && p.status !== statusFilter) return false
      if (stageFilter && p.current_stage !== stageFilter) return false
      if (typeFilter && p.process_type !== typeFilter) return false
      if (q) {
        const haystack = [p.name, p.process_type, p.description || ''].join(' ').toLowerCase()
        if (!haystack.includes(q)) return false
      }
      return true
    })

    rows = [...rows].sort((a, b) => {
      if (sortKey === 'name') return a.name.localeCompare(b.name)
      if (sortKey === 'created') {
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      }
      const aUpdated = new Date(a.updated_at || a.created_at).getTime()
      const bUpdated = new Date(b.updated_at || b.created_at).getTime()
      return bUpdated - aUpdated
    })

    return rows
  }, [processes, search, statusFilter, stageFilter, typeFilter, sortKey])

  function clearFilters() {
    setSearch('')
    setStatusFilter('')
    setStageFilter('')
    setTypeFilter('')
    setSortKey('updated')
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Processes"
        description="Create, monitor, and manage your business processes."
        actions={
          <Link to="/processes/new" className="btn btn-primary btn-sm gap-1.5">
            <span aria-hidden className="text-base leading-none">
              +
            </span>
            Create Process
          </Link>
        }
      />

      {error ? (
        <Alert tone="error">
          <div className="space-y-2">
            <p className="font-medium">Unable to load processes</p>
            <p>{error || 'Something went wrong while retrieving your processes.'}</p>
            <button type="button" className="btn btn-ghost btn-xs" onClick={() => void refresh()}>
              Retry
            </button>
          </div>
        </Alert>
      ) : null}

      <Panel>
        {/* Toolbar */}
        <div className="mb-5 space-y-3">
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1.4fr)_repeat(3,minmax(0,1fr))_minmax(0,0.9fr)]">
            <label className="block text-sm">
              <span className="sr-only">Search processes</span>
              <input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by name, type, or description"
                className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-slate-400"
              />
            </label>
            <label className="block text-sm">
              <span className="sr-only">Status</span>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className={selectClassName()}
                aria-label="Filter by status"
              >
                <option value="">All statuses</option>
                {statusOptions.map((s) => (
                  <option key={s} value={s}>
                    {formatProcessStatus(s)}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="sr-only">Current stage</span>
              <select
                value={stageFilter}
                onChange={(e) => setStageFilter(e.target.value)}
                className={selectClassName()}
                aria-label="Filter by stage"
              >
                {STAGE_FILTERS.map((s) => (
                  <option key={s.value || 'all'} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="sr-only">Process type</span>
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className={selectClassName()}
                aria-label="Filter by type"
              >
                <option value="">All types</option>
                {typeOptions.map((t) => (
                  <option key={t} value={t}>
                    {formatProcessType(t)}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="sr-only">Sort</span>
              <select
                value={sortKey}
                onChange={(e) => setSortKey(e.target.value as SortKey)}
                className={selectClassName()}
                aria-label="Sort processes"
              >
                <option value="updated">Recently updated</option>
                <option value="created">Recently created</option>
                <option value="name">Name</option>
              </select>
            </label>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-slate-500">
              {loading
                ? 'Loading processes…'
                : `${filtered.length} process${filtered.length === 1 ? '' : 'es'}${
                    filtersActive && processes.length !== filtered.length
                      ? ` of ${processes.length}`
                      : ''
                  }`}
            </p>
            {filtersActive ? (
              <button type="button" className="btn btn-ghost btn-xs" onClick={clearFilters}>
                Clear filters
              </button>
            ) : null}
          </div>
        </div>

        {loading ? (
          <>
            <div className="hidden space-y-3 md:block">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
            <div className="space-y-3 md:hidden">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-28 w-full" />
              ))}
            </div>
          </>
        ) : error && processes.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50/80 px-6 py-10 text-center">
            <p className="font-medium text-slate-800">Unable to load processes</p>
            <p className="mt-1 text-sm text-slate-600">
              Something went wrong while retrieving your processes.
            </p>
            <button
              type="button"
              className="btn btn-primary btn-sm mt-4"
              onClick={() => void refresh()}
            >
              Retry
            </button>
          </div>
        ) : processes.length === 0 ? (
          <div className="space-y-4 py-4">
            <EmptyState
              title="No processes yet"
              body="Create your first business process to start the BPMFlow journey."
            />
            <div className="text-center">
              <Link to="/processes/new" className="btn btn-primary btn-sm gap-1.5">
                <span aria-hidden>+</span>
                Create Process
              </Link>
            </div>
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No matching processes"
            body="Try adjusting your search or filters."
          />
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
                    <th className="pb-3 pr-4 font-medium">Last Updated</th>
                    <th className="pb-3 font-medium">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((p) => (
                    <tr key={p.id} className="border-b border-slate-50 last:border-0">
                      <td className="max-w-xs py-3.5 pr-4">
                        <Link
                          to={`/processes/${p.id}`}
                          className="font-medium text-slate-900 hover:underline"
                        >
                          {p.name}
                        </Link>
                        {p.description ? (
                          <p className="mt-0.5 line-clamp-1 text-xs text-slate-500">{p.description}</p>
                        ) : null}
                      </td>
                      <td className="py-3.5 pr-4 text-slate-600">{formatProcessType(p.process_type)}</td>
                      <td className="py-3.5 pr-4 text-slate-600">{formatProcessStatus(p.status)}</td>
                      <td className="py-3.5 pr-4">
                        <ProcessStageBadge stage={p.current_stage} />
                      </td>
                      <td className="whitespace-nowrap py-3.5 pr-4 text-slate-500">
                        {formatShortDate(p.created_at)}
                      </td>
                      <td className="whitespace-nowrap py-3.5 pr-4 text-slate-500">
                        {formatShortDate(p.updated_at)}
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
              {filtered.map((p) => (
                <article
                  key={p.id}
                  className="rounded-xl border border-slate-200 bg-slate-50/40 p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <Link
                        to={`/processes/${p.id}`}
                        className="font-medium text-slate-900 hover:underline"
                      >
                        {p.name}
                      </Link>
                      {p.description ? (
                        <p className="mt-0.5 line-clamp-2 text-xs text-slate-500">{p.description}</p>
                      ) : null}
                    </div>
                    <Link
                      to={`/processes/${p.id}`}
                      className="btn btn-ghost btn-xs shrink-0 font-medium"
                    >
                      View
                    </Link>
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-600">
                    <span>{formatProcessType(p.process_type)}</span>
                    <span className="text-slate-300">·</span>
                    <span>{formatProcessStatus(p.status)}</span>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                    <ProcessStageBadge stage={p.current_stage} />
                    <span className="text-xs text-slate-500">
                      Updated {formatShortDate(p.updated_at)}
                    </span>
                  </div>
                </article>
              ))}
            </div>
          </>
        )}
      </Panel>
    </div>
  )
}
