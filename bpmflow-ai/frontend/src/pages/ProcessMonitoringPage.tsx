import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { calculateProcessKpis, getProcessMonitoring } from '../services/apiClient'
import type { ProcessMonitoringReport } from '../types/api'
import { Alert, EmptyState, PageHeader, Panel, Skeleton } from '../components/ui/primitives'
import MonitoringTimeline from '../components/operations/MonitoringTimeline'
import KpiGrid from '../components/operations/KpiGrid'
import BottleneckList from '../components/operations/BottleneckList'
import ExceptionAnalyticsView from '../components/operations/ExceptionAnalyticsView'
import { durationLabel, operationsErrorMessage } from '../lib/operations'
import { formatDateTime } from '../components/process-cockpit/helpers'

export default function ProcessMonitoringPage() {
  const { processId = '' } = useParams()
  const [report, setReport] = useState<ProcessMonitoringReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    if (!processId) return
    setLoading(true)
    setError(null)
    try {
      setReport(await getProcessMonitoring(processId))
    } catch (err) {
      setReport(null)
      setError(operationsErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [processId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function onCalculate() {
    setBusy(true)
    setError(null)
    try {
      const kpis = await calculateProcessKpis(processId)
      setReport((current) => (current ? { ...current, kpis } : current))
    } catch (err) {
      setError(operationsErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  if (loading && !report) {
    return (
      <div aria-busy="true">
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <Link to="/monitoring" className="text-sm font-medium text-slate-500">
        ← Monitoring
      </Link>
      <PageHeader
        title="Process monitoring"
        description="Backend monitoring report for this process. Values are not calculated in the browser."
        actions={
          <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={() => void onCalculate()}>
            {busy ? 'Calculating…' : 'Recalculate KPIs'}
          </button>
        }
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      {!report ? (
        <EmptyState title="No monitoring data" body="GET /processes/{id}/monitoring did not return a report." />
      ) : (
        <>
          <Panel title="Overview">
            <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <dt className="text-xs uppercase text-slate-500">State</dt>
                <dd>{report.state}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-slate-500">Status</dt>
                <dd>{report.status}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-slate-500">Started</dt>
                <dd>{report.started_at ? formatDateTime(report.started_at) : '—'}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-slate-500">Duration</dt>
                <dd>{durationLabel(report.duration_seconds)}</dd>
              </div>
            </dl>
            <div className="mt-3 flex flex-wrap gap-2">
              <Link className="btn btn-ghost btn-sm" to={`/processes/${processId}`}>
                Process cockpit
              </Link>
              <Link className="btn btn-ghost btn-sm" to={`/recommendations?process=${processId}`}>
                TO-BE recommendations
              </Link>
            </div>
          </Panel>
          <Panel title="KPIs">
            <KpiGrid kpis={report.kpis} />
          </Panel>
          <Panel title="Timeline">
            <MonitoringTimeline events={report.timeline || []} />
          </Panel>
          <Panel title="Observed bottlenecks">
            <BottleneckList items={report.bottlenecks || []} />
          </Panel>
          <Panel title="Exception analytics">
            <ExceptionAnalyticsView data={report.exception_analytics} />
          </Panel>
        </>
      )}
    </div>
  )
}
