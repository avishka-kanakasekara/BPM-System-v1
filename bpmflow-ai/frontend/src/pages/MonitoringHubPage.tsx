import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listProcesses } from '../services/apiClient'
import type { ProcessRecord } from '../types/api'
import { Alert, EmptyState, PageHeader, Panel, Skeleton } from '../components/ui/primitives'
import { operationsErrorMessage } from '../lib/operations'

export default function MonitoringHubPage() {
  const [processes, setProcesses] = useState<ProcessRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setProcesses(await listProcesses())
    } catch (err) {
      setError(operationsErrorMessage(err))
      setProcesses([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return (
    <div className="space-y-6">
      <PageHeader
        title="Monitoring"
        description="Process-level KPIs, timeline, bottlenecks, and exception analytics. There is no organization-wide KPI API — open a process monitoring workspace."
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      <Panel>
        {loading ? (
          <div aria-busy="true">
            <Skeleton className="h-24 w-full" />
          </div>
        ) : processes.length === 0 ? (
          <EmptyState title="No processes" body="Monitoring is process-scoped. Create or open a process first." />
        ) : (
          <ul className="divide-y divide-slate-100">
            {processes.map((process) => (
              <li key={process.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                <div>
                  <p className="font-medium">{process.name}</p>
                  <p className="text-xs text-slate-500">
                    {process.current_stage} · {process.status}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Link className="btn btn-ghost btn-sm" to={`/processes/${process.id}/monitoring`}>
                    Open monitoring
                  </Link>
                  <Link className="btn btn-ghost btn-sm" to={`/recommendations?process=${process.id}`}>
                    TO-BE recommendations
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  )
}
