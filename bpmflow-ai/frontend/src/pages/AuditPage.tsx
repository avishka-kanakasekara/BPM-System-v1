import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  apiErrorMessage,
  listAuditLogs,
  listProcesses,
  type AuditLogRecord,
  type ProcessRecord,
} from '../services/apiClient'
import {
  Alert,
  EmptyState,
  PageHeader,
  Panel,
} from '../components/ui/primitives'

const PAGE_SIZE = 50

const ENTITY_TYPE_OPTIONS = [
  { value: '', label: 'All entities' },
  { value: 'process', label: 'Process' },
  { value: 'approval', label: 'Approval' },
  { value: 'exception', label: 'Exception' },
  { value: 'task', label: 'Task' },
]

type DatePreset = '' | 'today' | '7d' | '30d'

function auditErrorMessage(err: unknown): string {
  const status = (err as { response?: { status?: number } })?.response?.status
  if (status === 401) return 'Your session has expired. Please sign in again.'
  if (status === 403) return "You don't have permission to view audit information."
  if (status === 503) return 'The audit service is temporarily unavailable.'
  return apiErrorMessage(err)
}

function formatActionLabel(action: string): string {
  const map: Record<string, string> = {
    created: 'Created',
    updated: 'Updated',
    completed: 'Completed',
    PROCESS_CREATED: 'Process created',
    STAGE_UPDATED: 'Stage updated',
    APPROVAL_REQUESTED: 'Approval requested',
    APPROVED: 'Approval completed',
    REJECTED: 'Approval rejected',
    RISK_REVIEW: 'Risk review completed',
    EXCEPTION_CREATED: 'Exception created',
    EXCEPTION_OPENED: 'Exception created',
    EXCEPTION_RESOLVED: 'Exception resolved',
    EXCEPTION_RETRIED: 'Exception retried',
    START: 'Discovery started',
    EXECUTE: 'Execution started',
  }
  if (map[action]) return map[action]
  if (map[action.toUpperCase()]) return map[action.toUpperCase()]
  return action
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatEntityType(type: string): string {
  if (!type) return 'Entity'
  return type
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
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

function formatTimeShort(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function formatActor(performedBy: string | null | undefined): string {
  if (performedBy == null || performedBy === '') return 'System'
  return performedBy
}

function formatFieldKey(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string') return value || '—'
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function changeRows(
  oldValues: Record<string, unknown> | null | undefined,
  newValues: Record<string, unknown> | null | undefined,
): Array<{ key: string; before: string; after: string }> {
  const oldObj = oldValues || {}
  const newObj = newValues || {}
  const keys = Array.from(new Set([...Object.keys(oldObj), ...Object.keys(newObj)])).sort()
  return keys.map((key) => ({
    key,
    before: formatValue(oldObj[key]),
    after: formatValue(newObj[key]),
  }))
}

function withinDatePreset(timestamp: string, preset: DatePreset): boolean {
  if (!preset) return true
  const t = new Date(timestamp).getTime()
  if (Number.isNaN(t)) return false
  const now = Date.now()
  if (preset === 'today') {
    const start = new Date()
    start.setHours(0, 0, 0, 0)
    return t >= start.getTime()
  }
  if (preset === '7d') return t >= now - 7 * 24 * 60 * 60 * 1000
  if (preset === '30d') return t >= now - 30 * 24 * 60 * 60 * 1000
  return true
}

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-slate-200/70 ${className}`} />
}

function inputClass() {
  return 'h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none focus:border-slate-400'
}

export default function AuditPage() {
  const [rows, setRows] = useState<AuditLogRecord[]>([])
  const [processes, setProcesses] = useState<ProcessRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [entityType, setEntityType] = useState('')
  const [entityId, setEntityId] = useState('')
  const [entityIdDraft, setEntityIdDraft] = useState('')
  const [actionFilter, setActionFilter] = useState('')
  const [datePreset, setDatePreset] = useState<DatePreset>('')
  const [offset, setOffset] = useState(0)

  const [selected, setSelected] = useState<AuditLogRecord | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [logs, procs] = await Promise.all([
        listAuditLogs({
          entity_type: entityType || undefined,
          entity_id: entityId || undefined,
          limit: PAGE_SIZE,
          offset,
        }),
        listProcesses().catch(() => [] as ProcessRecord[]),
      ])
      setRows(logs)
      setProcesses(procs)
    } catch (err) {
      setError(auditErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [entityType, entityId, offset])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const processNameById = useMemo(() => {
    const map = new Map<string, string>()
    for (const p of processes) map.set(p.id, p.name)
    return map
  }, [processes])

  const actionOptions = useMemo(() => {
    const set = new Set<string>()
    for (const r of rows) {
      if (r.action) set.add(r.action)
    }
    return Array.from(set).sort()
  }, [rows])

  const entityTypeOptions = useMemo(() => {
    const fromData = new Set(ENTITY_TYPE_OPTIONS.map((o) => o.value).filter(Boolean))
    for (const r of rows) {
      if (r.entity_type) fromData.add(r.entity_type)
    }
    const extras = Array.from(fromData)
      .filter((v) => !ENTITY_TYPE_OPTIONS.some((o) => o.value === v))
      .sort()
      .map((v) => ({ value: v, label: formatEntityType(v) }))
    return [...ENTITY_TYPE_OPTIONS, ...extras]
  }, [rows])

  const displayed = useMemo(() => {
    return rows.filter((r) => {
      if (actionFilter && r.action !== actionFilter) return false
      if (!withinDatePreset(r.timestamp, datePreset)) return false
      return true
    })
  }, [rows, actionFilter, datePreset])

  const clientFiltersActive = Boolean(actionFilter || datePreset)
  const apiFiltersActive = Boolean(entityType || entityId)
  const filtersActive = clientFiltersActive || apiFiltersActive

  const rangeStart = rows.length === 0 ? 0 : offset + 1
  const rangeEnd = offset + rows.length
  const canPrev = offset > 0
  const canNext = rows.length === PAGE_SIZE

  function clearFilters() {
    setEntityType('')
    setEntityId('')
    setEntityIdDraft('')
    setActionFilter('')
    setDatePreset('')
    setOffset(0)
  }

  function applyEntityId() {
    setEntityId(entityIdDraft.trim())
    setOffset(0)
  }

  function entityLabel(row: AuditLogRecord): { title: string; subtitle: string } {
    const typeLabel = formatEntityType(row.entity_type)
    if (row.entity_type.toLowerCase() === 'process') {
      const name = processNameById.get(row.entity_id)
      return {
        title: typeLabel,
        subtitle: name || row.entity_id,
      }
    }
    return {
      title: typeLabel,
      subtitle: row.entity_id,
    }
  }

  function isProcessEntity(row: AuditLogRecord): boolean {
    return row.entity_type.toLowerCase() === 'process'
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Audit Trail"
        description="Track important actions and decisions across your business processes."
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

      <Panel>
        <div className="mb-5 space-y-3">
          <div className="grid gap-3 lg:grid-cols-4">
            <label className="block text-sm">
              <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-500">
                Entity type
              </span>
              <select
                value={entityType}
                onChange={(e) => {
                  setEntityType(e.target.value)
                  setOffset(0)
                }}
                className={inputClass()}
                aria-label="Filter by entity type"
              >
                {entityTypeOptions.map((o) => (
                  <option key={o.value || 'all'} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="block text-sm lg:col-span-2">
              <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-500">
                Entity ID
              </span>
              <div className="flex gap-2">
                <input
                  value={entityIdDraft}
                  onChange={(e) => setEntityIdDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      applyEntityId()
                    }
                  }}
                  placeholder="Optional entity identifier"
                  className={inputClass()}
                  aria-label="Filter by entity ID"
                />
                <button type="button" className="btn btn-ghost btn-sm shrink-0" onClick={applyEntityId}>
                  Apply
                </button>
              </div>
            </label>

            <label className="block text-sm">
              <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-500">
                Date
              </span>
              <select
                value={datePreset}
                onChange={(e) => setDatePreset(e.target.value as DatePreset)}
                className={inputClass()}
                aria-label="Filter by date"
              >
                <option value="">All loaded dates</option>
                <option value="today">Today</option>
                <option value="7d">Last 7 days</option>
                <option value="30d">Last 30 days</option>
              </select>
            </label>
          </div>

          <div className="flex flex-wrap items-end justify-between gap-3">
            <label className="block min-w-[12rem] flex-1 text-sm sm:max-w-xs">
              <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-500">
                Action
              </span>
              <select
                value={actionFilter}
                onChange={(e) => setActionFilter(e.target.value)}
                className={inputClass()}
                aria-label="Filter by action"
              >
                <option value="">All loaded actions</option>
                {actionOptions.map((a) => (
                  <option key={a} value={a}>
                    {formatActionLabel(a)}
                  </option>
                ))}
              </select>
            </label>

            {filtersActive ? (
              <button type="button" className="btn btn-ghost btn-xs" onClick={clearFilters}>
                Clear Filters
              </button>
            ) : null}
          </div>

          {clientFiltersActive ? (
            <p className="text-xs text-slate-500">
              Action and date filters apply only to the events on this page (API limit {PAGE_SIZE}).
            </p>
          ) : null}
        </div>

        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <EmptyState
            title="No audit events found."
            body={
              filtersActive
                ? 'Try adjusting entity filters or clear them to broaden results.'
                : 'Actions across processes, approvals, and exceptions will appear here.'
            }
          />
        ) : displayed.length === 0 ? (
          <div className="space-y-4">
            <EmptyState
              title="No audit events match your filters."
              body="Action and date filters only apply to the currently loaded page."
            />
            <div className="text-center">
              <button type="button" className="btn btn-ghost btn-sm" onClick={clearFilters}>
                Clear Filters
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* Desktop table */}
            <div className="hidden overflow-x-auto md:block">
              <table className="min-w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-100 text-xs font-medium uppercase tracking-wide text-slate-500">
                    <th className="pb-3 pr-4 font-medium">Time</th>
                    <th className="pb-3 pr-4 font-medium">Action</th>
                    <th className="pb-3 pr-4 font-medium">Entity</th>
                    <th className="pb-3 pr-4 font-medium">Performed By</th>
                    <th className="pb-3 font-medium">Details</th>
                  </tr>
                </thead>
                <tbody>
                  {displayed.map((row) => {
                    const entity = entityLabel(row)
                    return (
                      <tr key={row.id} className="border-b border-slate-50 last:border-0">
                        <td className="whitespace-nowrap py-3.5 pr-4 text-slate-500">
                          {formatTimeShort(row.timestamp)}
                        </td>
                        <td className="py-3.5 pr-4">
                          <span className="font-medium text-slate-900">
                            {formatActionLabel(row.action)}
                          </span>
                        </td>
                        <td className="max-w-[16rem] py-3.5 pr-4">
                          <p className="font-medium text-slate-800">{entity.title}</p>
                          <p className="truncate text-xs text-slate-500">{entity.subtitle}</p>
                        </td>
                        <td className="max-w-[10rem] truncate py-3.5 pr-4 text-slate-600">
                          {formatActor(row.performed_by)}
                        </td>
                        <td className="py-3.5">
                          <button
                            type="button"
                            className="text-sm font-medium text-slate-700 hover:text-slate-900"
                            onClick={() => setSelected(row)}
                          >
                            View
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <ul className="space-y-3 md:hidden">
              {displayed.map((row) => {
                const entity = entityLabel(row)
                return (
                  <li
                    key={row.id}
                    className="rounded-xl border border-slate-200 bg-slate-50/40 p-4"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="font-medium text-slate-900">
                          {formatActionLabel(row.action)}
                        </p>
                        <p className="mt-1 text-sm text-slate-600">
                          {entity.title}
                          <span className="text-slate-400"> · </span>
                          <span className="break-all text-xs text-slate-500">{entity.subtitle}</span>
                        </p>
                        <p className="mt-2 text-xs text-slate-500">
                          {formatTimeShort(row.timestamp)} · {formatActor(row.performed_by)}
                        </p>
                      </div>
                      <button
                        type="button"
                        className="btn btn-ghost btn-xs shrink-0"
                        onClick={() => setSelected(row)}
                      >
                        Details
                      </button>
                    </div>
                  </li>
                )
              })}
            </ul>

            <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
              <p className="text-xs text-slate-500">
                {rows.length === 0
                  ? 'No events'
                  : `Showing ${rangeStart}–${rangeEnd}`}
                {clientFiltersActive && displayed.length !== rows.length
                  ? ` · ${displayed.length} match filters`
                  : ''}
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  disabled={!canPrev || loading}
                  onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
                >
                  Previous
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  disabled={!canNext || loading}
                  onClick={() => setOffset((o) => o + PAGE_SIZE)}
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </Panel>

      {selected ? (
        <div className="modal modal-open">
          <div
            className="modal-box max-w-xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="audit-event-title"
          >
            <h3 id="audit-event-title" className="text-lg font-semibold text-slate-900">
              Audit Event
            </h3>
            <p className="mt-1 text-sm text-slate-500">{formatActionLabel(selected.action)}</p>

            <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Action</dt>
                <dd className="mt-1 font-medium text-slate-900">
                  {formatActionLabel(selected.action)}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Timestamp</dt>
                <dd className="mt-1 text-slate-800">{formatDateTime(selected.timestamp)}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Entity Type</dt>
                <dd className="mt-1 text-slate-800">{formatEntityType(selected.entity_type)}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Entity ID</dt>
                <dd className="mt-1 break-all font-mono text-xs text-slate-700">
                  {selected.entity_id}
                </dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-xs uppercase tracking-wide text-slate-500">Performed By</dt>
                <dd className="mt-1 text-slate-800">{formatActor(selected.performed_by)}</dd>
              </div>
              {isProcessEntity(selected) && processNameById.get(selected.entity_id) ? (
                <div className="sm:col-span-2">
                  <dt className="text-xs uppercase tracking-wide text-slate-500">Process</dt>
                  <dd className="mt-1 text-slate-800">
                    {processNameById.get(selected.entity_id)}
                  </dd>
                </div>
              ) : null}
            </dl>

            <div className="mt-6">
              <h4 className="text-sm font-semibold text-slate-900">What Changed</h4>
              {changeRows(selected.old_values, selected.new_values).length === 0 ? (
                <p className="mt-2 text-sm text-slate-500">No field-level changes were recorded.</p>
              ) : (
                <ul className="mt-3 space-y-2">
                  {changeRows(selected.old_values, selected.new_values).map((c) => (
                    <li
                      key={c.key}
                      className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2 text-sm"
                    >
                      <p className="font-medium text-slate-800">{formatFieldKey(c.key)}</p>
                      <p className="mt-1 text-xs text-slate-600">
                        <span className="text-slate-500">Before:</span> {c.before}
                      </p>
                      <p className="text-xs text-slate-600">
                        <span className="text-slate-500">After:</span> {c.after}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="modal-action flex-col gap-2 sm:flex-row sm:justify-between">
              {isProcessEntity(selected) ? (
                <Link
                  to={`/processes/${selected.entity_id}`}
                  className="btn btn-ghost btn-sm"
                  onClick={() => setSelected(null)}
                >
                  View Process
                </Link>
              ) : (
                <span />
              )}
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => setSelected(null)}
              >
                Close
              </button>
            </div>
          </div>
          <button
            type="button"
            className="modal-backdrop bg-slate-900/40"
            aria-label="Close audit event"
            onClick={() => setSelected(null)}
          />
        </div>
      ) : null}
    </div>
  )
}
