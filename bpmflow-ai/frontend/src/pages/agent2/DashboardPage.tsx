import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  apiErrorMessage,
  getAgent2Dashboard,
  listAgent2AuditLogs,
  listProcesses,
  type Agent2AuditLog,
  type Agent2Dashboard,
} from '../../services/apiClient'
import {
  Alert,
  Badge,
  EmptyState,
  PageHeader,
  Panel,
  Spinner,
} from '../../components/ui/primitives'

function toneForStatus(status: string): 'good' | 'bad' | 'neutral' | 'warn' {
  const s = status.toUpperCase()
  if (s === 'SUCCESS') return 'good'
  if (s === 'FAILED' || s === 'BLOCKED') return 'bad'
  if (s === 'RETRYING') return 'warn'
  return 'neutral'
}

export default function Agent2DashboardPage() {
  const [processId, setProcessId] = useState('')
  const [options, setOptions] = useState<{ id: string; name: string }[]>([])
  const [dashboard, setDashboard] = useState<Agent2Dashboard | null>(null)
  const [audit, setAudit] = useState<Agent2AuditLog[]>([])
  const [error, setError] = useState<string | null>(null)
  const [processListError, setProcessListError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  async function refresh() {
    setLoading(true)
    try {
      const [dash, logs] = await Promise.all([
        getAgent2Dashboard(processId || undefined),
        listAgent2AuditLogs(10),
      ])
      setDashboard(dash)
      setAudit(logs)
      setError(null)
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void listProcesses()
      .then((rows) => {
        setOptions(rows.map((r) => ({ id: r.id, name: r.name })))
        setProcessListError(null)
      })
      .catch((err) => {
        setOptions([])
        setProcessListError(apiErrorMessage(err))
      })
  }, [])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => void refresh(), 15000)
    return () => window.clearInterval(timer)
  }, [processId])

  const m = dashboard?.metrics

  return (
    <div className="space-y-6">
      <PageHeader
        title="Agent 2 — Execution dashboard"
        description="Workflow execution health, metrics, and recent authorized tool runs."
        actions={
          <Link
            to="/agent2/tools"
            className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white"
          >
            Open tools
          </Link>
        }
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      {processListError ? (
        <Alert tone="warning">Process filter unavailable: {processListError}</Alert>
      ) : null}

      <Panel title="Scope">
        <div className="flex flex-wrap gap-3">
          <select
            value={processId}
            onChange={(e) => setProcessId(e.target.value)}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">All processes</option>
            {options.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => void refresh()}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            Refresh
          </button>
        </div>
      </Panel>

      {loading && !dashboard ? (
        <Spinner />
      ) : !dashboard ? (
        <EmptyState title="No dashboard data" body="Agent 2 metrics will appear after executions." />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Panel title="Agent status">
              <p className="text-lg font-semibold">{dashboard.status}</p>
              <Badge tone={dashboard.health === 'healthy' ? 'good' : 'warn'}>
                {dashboard.health}
              </Badge>
            </Panel>
            <Panel title="Success rate">
              <p className="text-2xl font-semibold">
                {m ? `${Math.round(m.success_rate * 100)}%` : '—'}
              </p>
              <p className="text-xs text-slate-500">
                {m?.successful ?? 0} / {m?.total_executions ?? 0} executions
              </p>
            </Panel>
            <Panel title="Avg latency">
              <p className="text-2xl font-semibold">{m?.average_latency_ms ?? 0} ms</p>
            </Panel>
            <Panel title="Open exceptions">
              <p className="text-2xl font-semibold">{m?.open_exceptions ?? 0}</p>
              <Link to="/agent2/receipts" className="text-xs text-indigo-600">
                View history →
              </Link>
            </Panel>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Execution breakdown">
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <dt className="text-slate-500">Running / total</dt>
                  <dd className="font-medium">{m?.total_executions ?? 0}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Failed</dt>
                  <dd className="font-medium text-red-600">{m?.failed ?? 0}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Blocked</dt>
                  <dd className="font-medium">{m?.blocked ?? 0}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Retrying</dt>
                  <dd className="font-medium">{m?.retrying ?? 0}</dd>
                </div>
              </dl>
            </Panel>
            <Panel title="Tool usage">
              {Object.keys(dashboard.tool_usage || {}).length === 0 ? (
                <p className="text-sm text-slate-500">No tool runs yet.</p>
              ) : (
                <ul className="space-y-1 text-sm">
                  {Object.entries(dashboard.tool_usage)
                    .sort((a, b) => b[1] - a[1])
                    .map(([tool, count]) => (
                      <li key={tool} className="flex justify-between">
                        <span>{tool}</span>
                        <span className="font-mono text-slate-600">{count}</span>
                      </li>
                    ))}
                </ul>
              )}
            </Panel>
          </div>

          <Panel title="Recent executions">
            {dashboard.recent_executions.length === 0 ? (
              <EmptyState title="No executions" body="Authorized runs appear here in real time." />
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="border-b text-xs uppercase text-slate-500">
                    <tr>
                      <th className="px-2 py-2">Tool</th>
                      <th className="px-2 py-2">Status</th>
                      <th className="px-2 py-2">Latency</th>
                      <th className="px-2 py-2">Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dashboard.recent_executions.map((r, idx) => {
                      const id = String(r.execution_id || r.id || idx)
                      const status = String(r.status || '')
                      return (
                        <tr key={id} className="border-b border-slate-50">
                          <td className="px-2 py-2">{String(r.tool_name || '—')}</td>
                          <td className="px-2 py-2">
                            <Badge tone={toneForStatus(status)}>{status}</Badge>
                          </td>
                          <td className="px-2 py-2">{String(r.latency_ms ?? '—')} ms</td>
                          <td className="px-2 py-2">
                            {r.execution_id || r.id ? (
                              <Link
                                to={`/agent2/executions/${id}`}
                                className="text-indigo-600 hover:underline"
                              >
                                View
                              </Link>
                            ) : (
                              '—'
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          <Panel title="Recent audit events">
            {audit.length === 0 ? (
              <p className="text-sm text-slate-500">No audit entries.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {audit.map((a) => (
                  <li key={a.id} className="flex flex-wrap gap-2 border-b border-slate-50 pb-2">
                    <Badge tone={a.allowed ? 'good' : 'bad'}>
                      {a.allowed ? 'ALLOWED' : 'DENIED'}
                    </Badge>
                    <span className="font-medium">{a.action}</span>
                    <span className="text-slate-500">{a.reason}</span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </>
      )}
    </div>
  )
}
