import { useEffect, useState } from 'react'
import { apiErrorMessage, getProcessKpis, listProcesses } from '../../services/apiClient'
import {
  Alert,
  EmptyState,
  PageHeader,
  Panel,
  Spinner,
} from '../../components/ui/primitives'

export default function Agent2KpisPage() {
  const [processId, setProcessId] = useState('')
  const [options, setOptions] = useState<{ id: string; name: string }[]>([])
  const [kpis, setKpis] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    void listProcesses()
      .then((rows) => setOptions(rows.map((r) => ({ id: r.id, name: r.name }))))
      .catch(() => undefined)
  }, [])

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const data = await getProcessKpis(processId || undefined)
      setKpis(data)
    } catch (err) {
      setError(apiErrorMessage(err))
      setKpis(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  return (
    <div className="space-y-6">
      <PageHeader
        title="Agent 2 — KPIs"
        description="Execution metrics from the Agent 2 analytics engine."
      />
      {error ? <Alert tone="error">{error}</Alert> : null}

      <Panel title="Scope">
        <div className="flex flex-wrap gap-3">
          <select
            value={processId}
            onChange={(e) => setProcessId(e.target.value)}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">All / aggregate</option>
            {options.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => void load()}
            className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white"
          >
            Refresh
          </button>
        </div>
      </Panel>

      <Panel title="KPI payload">
        {loading ? (
          <Spinner />
        ) : !kpis ? (
          <EmptyState title="No KPI data" body="Run Agent 2 execution to populate metrics." />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(kpis).map(([key, value]) => (
              <div key={key} className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  {key.replace(/_/g, ' ')}
                </p>
                <p className="mt-1 break-all text-lg font-semibold text-slate-900">
                  {typeof value === 'object' ? JSON.stringify(value) : String(value ?? '—')}
                </p>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  )
}
