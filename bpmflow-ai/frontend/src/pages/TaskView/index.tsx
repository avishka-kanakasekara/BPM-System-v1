import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listDiscoveredProcesses, ProcessSummary } from '../../services/apiClient'

function TaskView() {
  const [rows, setRows] = useState<ProcessSummary[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listDiscoveredProcesses()
      .then(setRows)
      .catch((err) => setError((err as Error).message || 'Could not load processes'))
  }, [])

  return (
    <div className="mx-auto max-w-5xl p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold text-gray-900">Saved workflows</h1>
        <Link className="text-sm font-medium text-indigo-700 hover:underline" to="/">
          Discover another
        </Link>
      </div>
      {error && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      )}
      {rows.length === 0 && !error ? (
        <p className="text-gray-600">No discovered processes yet. Upload documents on the home page.</p>
      ) : (
        <ul className="space-y-3">
          {rows.map((row) => (
            <li key={row.process_id} className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
              <p className="font-semibold text-gray-900">{row.name}</p>
              <p className="text-sm text-gray-600">
                {row.activity_count} steps · {row.discovery_status || row.status}
              </p>
              <p className="mt-1 font-mono text-xs text-gray-400">{row.process_id}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default TaskView
