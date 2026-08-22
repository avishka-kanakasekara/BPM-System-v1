import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  listDiscoveredProcesses,
  listProcesses,
  ProcessRecord,
  ProcessSummary,
  startProcess,
} from '../../services/apiClient'

function apiErrorMessage(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  if (typeof detail === 'string') {
    return detail
  }
  return (err as Error).message || 'Request failed'
}

function TaskView() {
  const [discovered, setDiscovered] = useState<ProcessSummary[]>([])
  const [orchestrated, setOrchestrated] = useState<ProcessRecord[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setError(null)
    try {
      const [a1, a4] = await Promise.all([
        listDiscoveredProcesses().catch(() => [] as ProcessSummary[]),
        listProcesses().catch((err) => {
          throw err
        }),
      ])
      setDiscovered(a1)
      setOrchestrated(a4)
    } catch (err) {
      // Discovery list may work without auth; orchestrator list needs a Bearer token.
      setError(apiErrorMessage(err))
      try {
        setDiscovered(await listDiscoveredProcesses())
      } catch {
        setDiscovered([])
      }
      setOrchestrated([])
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function onStart(processId: string) {
    setBusyId(processId)
    setMessage(null)
    setError(null)
    try {
      const result = await startProcess(processId)
      setMessage(
        `Started ${processId}: stage=${result?.process?.current_stage ?? 'unknown'}; ` +
          `${result?.success ? 'ok' : result?.message || 'Agent 1 unavailable'}`,
      )
      await refresh()
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="mx-auto max-w-5xl p-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Workflows</h1>
          <p className="mt-1 text-gray-600">
            Agent 1 discoveries and Agent 4 orchestrated processes. Start moves a DRAFT
            process into DISCOVERING.
          </p>
        </div>
        <Link className="text-sm font-medium text-indigo-700 hover:underline" to="/">
          Discover another
        </Link>
      </div>

      {error ? (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      ) : null}
      {message ? (
        <div className="mb-4 rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          {message}
        </div>
      ) : null}

      <section className="mb-10">
        <h2 className="mb-3 text-lg font-semibold text-gray-900">Orchestrated processes</h2>
        {orchestrated.length === 0 ? (
          <p className="text-sm text-gray-500">
            No orchestrator processes yet (or sign in so the API can authorize the list).
          </p>
        ) : (
          <ul className="space-y-3">
            {orchestrated.map((row) => (
              <li
                key={row.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
              >
                <div>
                  <p className="font-semibold text-gray-900">{row.name}</p>
                  <p className="text-sm text-gray-600">
                    {row.process_type} · stage <span className="font-medium">{row.current_stage}</span>
                  </p>
                  <p className="mt-1 font-mono text-xs text-gray-400">{row.id}</p>
                </div>
                {row.current_stage === 'DRAFT' ? (
                  <button
                    type="button"
                    onClick={() => void onStart(row.id)}
                    disabled={busyId !== null}
                    className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {busyId === row.id ? 'Starting…' : 'Start'}
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-gray-900">Agent 1 discoveries</h2>
        {discovered.length === 0 ? (
          <p className="text-sm text-gray-500">
            No discovered processes yet. Upload documents on the home page.
          </p>
        ) : (
          <ul className="space-y-3">
            {discovered.map((row) => (
              <li
                key={row.process_id}
                className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
              >
                <p className="font-semibold text-gray-900">{row.name}</p>
                <p className="text-sm text-gray-600">
                  {row.activity_count} steps · {row.discovery_status || row.status}
                </p>
                <p className="mt-1 font-mono text-xs text-gray-400">{row.process_id}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

export default TaskView
