import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { listExceptions, listProcesses } from '../services/apiClient'
import type { ExceptionRecord, ProcessRecord } from '../types/api'
import { Alert, EmptyState, ExceptionStatusBadge, PageHeader, Panel, Skeleton } from '../components/ui/primitives'
import { formatDateTime } from '../components/process-cockpit/helpers'
import { operationsErrorMessage } from '../lib/operations'

export default function ExceptionsPage() {
  const [rows, setRows] = useState<ExceptionRecord[]>([])
  const [processes, setProcesses] = useState<ProcessRecord[]>([])
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const processName = useMemo(() => {
    const map = new Map(processes.map((p) => [p.id, p.name]))
    return (id: string | null | undefined) => (id ? map.get(id) || id : '—')
  }, [processes])

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [exceptions, procs] = await Promise.all([
        listExceptions(status || undefined),
        listProcesses().catch(() => [] as ProcessRecord[]),
      ])
      setRows(exceptions)
      setProcesses(procs)
    } catch (err) {
      setError(operationsErrorMessage(err))
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [status])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return (
    <div className="space-y-6">
      <PageHeader
        title="Exceptions"
        description="Tenant-scoped process exceptions from GET /api/v1/exceptions. Resolve, retry, and fail are explicit actions on the detail page."
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      <Panel title="Filter">
        <label className="text-sm">
          Status
          <select className="select select-bordered mt-1 w-full max-w-xs" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All</option>
            <option value="open">open</option>
            <option value="in_progress">in_progress</option>
            <option value="resolved">resolved</option>
            <option value="ignored">ignored</option>
          </select>
        </label>
      </Panel>
      <Panel>
        {loading ? (
          <div aria-busy="true" className="space-y-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : rows.length === 0 ? (
          <EmptyState title="No exceptions" body="No exception records were returned for this tenant and filter." />
        ) : (
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Title</th>
                  <th>Process</th>
                  <th>Status</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <Link className="link font-medium" to={`/exceptions/${row.id}`}>
                        {row.exception_code || row.type}
                      </Link>
                    </td>
                    <td>{row.title || row.description}</td>
                    <td>
                      {row.process_id ? (
                        <Link className="link" to={`/processes/${row.process_id}`}>
                          {processName(row.process_id)}
                        </Link>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>
                      <ExceptionStatusBadge status={row.status} />
                    </td>
                    <td className="whitespace-nowrap text-sm">{formatDateTime(row.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  )
}
