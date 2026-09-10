import { useEffect, useState } from 'react'
import {
  apiErrorMessage,
  listExecutionReceipts,
  type ExecutionReceipt,
} from '../../services/apiClient'
import {
  Alert,
  Badge,
  EmptyState,
  PageHeader,
  Panel,
  Spinner,
} from '../../components/ui/primitives'

export default function Agent2ReceiptsPage() {
  const [rows, setRows] = useState<ExecutionReceipt[]>([])
  const [processId, setProcessId] = useState('')
  const [status, setStatus] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  async function refresh() {
    setLoading(true)
    try {
      const data = await listExecutionReceipts({
        process_id: processId || undefined,
        status: status || undefined,
        limit: 100,
      })
      setRows(data)
      setError(null)
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
  }, [])

  return (
    <div className="space-y-6">
      <PageHeader
        title="Agent 2 — Execution receipts"
        description="Idempotent tool execution receipts with latency and error classification."
      />
      {error ? <Alert tone="error">{error}</Alert> : null}

      <Panel title="Filters">
        <div className="flex flex-wrap gap-3">
          <input
            placeholder="Process ID"
            value={processId}
            onChange={(e) => setProcessId(e.target.value)}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">Any status</option>
            <option value="SUCCESS">SUCCESS</option>
            <option value="FAILED">FAILED</option>
            <option value="RETRYING">RETRYING</option>
          </select>
          <button
            type="button"
            onClick={() => void refresh()}
            className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white"
          >
            Apply
          </button>
        </div>
      </Panel>

      <Panel>
        {loading ? (
          <Spinner />
        ) : rows.length === 0 ? (
          <EmptyState title="No receipts" body="Receipts appear after authorized Agent 2 tool runs." />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-slate-100 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-2 py-2">When</th>
                  <th className="px-2 py-2">Tool</th>
                  <th className="px-2 py-2">Status</th>
                  <th className="px-2 py-2">Latency</th>
                  <th className="px-2 py-2">Process / Task</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b border-slate-50 align-top">
                    <td className="px-2 py-3 whitespace-nowrap text-slate-500">
                      {new Date(r.created_at).toLocaleString()}
                    </td>
                    <td className="px-2 py-3">
                      <p className="font-medium">{r.tool_name}</p>
                      <p className="text-xs text-slate-500">{r.action} · attempt {r.attempt_number}</p>
                    </td>
                    <td className="px-2 py-3">
                      <Badge tone={r.status === 'SUCCESS' ? 'good' : 'bad'}>{r.status}</Badge>
                      {r.error_message ? (
                        <p className="mt-1 max-w-xs text-xs text-red-600">{r.error_message}</p>
                      ) : null}
                    </td>
                    <td className="px-2 py-3">{r.latency_ms != null ? `${r.latency_ms} ms` : '—'}</td>
                    <td className="px-2 py-3 font-mono text-xs text-slate-500">
                      <div>{r.process_id}</div>
                      <div>{r.task_id}</div>
                    </td>
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
