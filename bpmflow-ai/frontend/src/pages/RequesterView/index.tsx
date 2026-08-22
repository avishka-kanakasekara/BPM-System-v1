import { FormEvent, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { AgentMessage, discoverProcess } from '../../services/apiClient'

function fileKey(file: File) {
  return `${file.name}:${file.size}:${file.lastModified}`
}

function RequesterView() {
  const [files, setFiles] = useState<File[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<AgentMessage | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  function addFiles(incoming: FileList | File[]) {
    const next = Array.from(incoming)
    setFiles((current) => {
      const seen = new Set(current.map(fileKey))
      const merged = [...current]
      for (const file of next) {
        const key = fileKey(file)
        if (seen.has(key)) {
          continue
        }
        seen.add(key)
        merged.push(file)
      }
      return merged
    })
    setError(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  function removeFile(index: number) {
    setFiles((current) => current.filter((_, itemIndex) => itemIndex !== index))
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (!files.length) {
      setError('Choose at least one PDF, DOCX, or CSV file.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const message = await discoverProcess(files)
      setResult(message)
    } catch (err) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (err as Error).message ||
        'Discovery failed'
      setError(String(detail))
    } finally {
      setLoading(false)
    }
  }

  const activities = result?.payload.activities ?? []
  const missing = result?.payload.missing_or_contradictory_fields ?? []
  const discoveryErrors = result?.payload.discovery_errors ?? []

  return (
    <div className="mx-auto max-w-5xl p-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Discover a process</h1>
          <p className="mt-1 text-gray-600">
            Upload SOPs, purchase requests, quotations, or an event-log CSV. Agent 1 extracts the
            workflow and stores it in Supabase.
          </p>
        </div>
        <Link className="text-sm font-medium text-indigo-700 hover:underline" to="/tasks">
          View saved workflows
        </Link>
      </div>

      <form onSubmit={onSubmit} className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <label className="block text-sm font-medium text-gray-700">Documents</label>
        <p className="mt-1 text-sm text-gray-500">
          Add several PDF, DOCX, or CSV files. You can pick more than one at a time, or click Add
          files again to include documents from another folder.
        </p>
        <input
          ref={fileInputRef}
          className="sr-only"
          type="file"
          multiple
          accept=".pdf,.docx,.csv,application/pdf,text/csv,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          onChange={(event) => addFiles(event.target.files ?? [])}
        />
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="rounded-md border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm font-semibold text-indigo-700 hover:bg-indigo-100"
          >
            Add files
          </button>
          {files.length > 0 && (
            <button
              type="button"
              onClick={() => setFiles([])}
              className="rounded-md border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Clear all
            </button>
          )}
        </div>
        {files.length > 0 && (
          <ul className="mt-4 divide-y divide-gray-100 rounded-lg border border-gray-200">
            {files.map((file, index) => (
              <li key={fileKey(file)} className="flex items-center justify-between gap-3 px-4 py-2 text-sm">
                <span className="min-w-0 truncate text-gray-800">
                  {file.name}{' '}
                  <span className="text-gray-500">({Math.round(file.size / 1024)} KB)</span>
                </span>
                <button
                  type="button"
                  onClick={() => removeFile(index)}
                  className="shrink-0 text-sm font-medium text-red-600 hover:text-red-700"
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
        <button
          type="submit"
          disabled={loading}
          className="mt-4 rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-60"
        >
          {loading ? 'Discovering…' : `Run Agent 1${files.length ? ` (${files.length} files)` : ''}`}
        </button>
      </form>

      {error && (
        <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      )}

      {result && (
        <div className="mt-8 space-y-6">
          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <p className="text-sm text-gray-500">Process ID</p>
            <p className="font-mono text-sm text-gray-800">{result.process_id}</p>
            <h2 className="mt-3 text-xl font-semibold text-gray-900">
              {result.payload.process_name || 'Discovered process'}
            </h2>
            <p className="mt-1 text-sm text-gray-600">
              Status <span className="font-medium">{result.status}</span>
              {' · '}
              Confidence {(result.overall_confidence * 100).toFixed(0)}%
            </p>
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <h3 className="text-lg font-semibold text-gray-900">Workflow from Agent 1</h3>
            {activities.length === 0 ? (
              <p className="mt-2 text-sm text-gray-600">No activities could be extracted from the upload.</p>
            ) : (
              <ol className="mt-4 space-y-3">
                {activities.map((activity, index) => (
                  <li key={`${activity.name}-${index}`} className="flex gap-4 rounded-lg bg-gray-50 p-4">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-sm font-semibold text-white">
                      {index + 1}
                    </span>
                    <div>
                      <p className="font-medium text-gray-900">{activity.name}</p>
                      <p className="text-sm text-gray-600">
                        Actor: {activity.actor || 'unknown'}
                        {activity.avg_duration != null ? ` · Wait ${activity.avg_duration}h` : ''}
                      </p>
                      {activity.entry_conditions && activity.entry_conditions.length > 0 && (
                        <p className="mt-1 text-xs text-gray-500">
                          Entry: {activity.entry_conditions.join('; ')}
                        </p>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </div>

          {discoveryErrors.length > 0 && (
            <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              {discoveryErrors.join(' · ')}
            </div>
          )}

          {missing.length > 0 && (
            <details className="rounded-xl border border-gray-200 bg-white p-4 text-sm text-gray-600">
              <summary className="cursor-pointer font-medium text-gray-800">
                Missing or contradictory fields ({missing.length})
              </summary>
              <ul className="mt-2 list-disc pl-5">
                {missing.map((field) => (
                  <li key={field}>{field}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  )
}

export default RequesterView
