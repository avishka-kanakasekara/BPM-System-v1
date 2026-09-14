import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { generateTobeRecommendations, listProcesses, listTobeRecommendations } from '../services/apiClient'
import type { ProcessRecord, TobeRecommendationRecord } from '../types/api'
import { Alert, EmptyState, PageHeader, Panel, Skeleton } from '../components/ui/primitives'
import EvidenceList from '../components/operations/EvidenceList'
import { operationsErrorMessage } from '../lib/operations'

export default function TobeRecommendationsPage() {
  const [params, setParams] = useSearchParams()
  const selectedProcess = params.get('process') || ''
  const [processes, setProcesses] = useState<ProcessRecord[]>([])
  const [rows, setRows] = useState<TobeRecommendationRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const procs = await listProcesses()
      setProcesses(procs)
      if (selectedProcess) {
        setRows(await listTobeRecommendations(selectedProcess))
      } else {
        setRows([])
      }
    } catch (err) {
      setError(operationsErrorMessage(err))
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [selectedProcess])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function onGenerate() {
    if (!selectedProcess) {
      setError('Select a process before generating recommendations.')
      return
    }
    setGenerating(true)
    setError(null)
    setNotice(null)
    try {
      const created = await generateTobeRecommendations(selectedProcess)
      setRows(created)
      setNotice(
        created.length === 0
          ? 'Insufficient evidence. The backend returned no TO-BE recommendations.'
          : `Generated ${created.length} recommendation(s). Review is a separate human action.`,
      )
    } catch (err) {
      setError(operationsErrorMessage(err))
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="TO-BE Process Recommendations"
        description="Human-reviewed process improvement proposals from GET/POST /api/v1/processes/{id}/recommendations. These are not Agent 2 optimizations or Agent 3 resource recommendations."
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      {notice ? <Alert tone="info">{notice}</Alert> : null}
      <Panel title="Process">
        <label className="text-sm">
          Process
          <select
            className="select select-bordered mt-1 w-full max-w-lg"
            value={selectedProcess}
            onChange={(e) => {
              const value = e.target.value
              if (value) setParams({ process: value })
              else setParams({})
            }}
          >
            <option value="">Select a process</option>
            {processes.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="btn btn-primary btn-sm mt-4"
          disabled={!selectedProcess || generating}
          onClick={() => void onGenerate()}
        >
          {generating ? 'Generating…' : 'Generate recommendations'}
        </button>
        <p className="mt-2 text-xs text-slate-500">
          Generation is explicit. Opening this page does not generate recommendations. Accepting a recommendation does not activate a workflow.
        </p>
      </Panel>
      <Panel title="Recommendations">
        {!selectedProcess ? (
          <EmptyState title="Select a process" body="TO-BE recommendations are process-scoped. There is no global recommendation list API." />
        ) : loading ? (
          <div aria-busy="true">
            <Skeleton className="h-24 w-full" />
          </div>
        ) : rows.length === 0 ? (
          <EmptyState
            title="No recommendations"
            body="No persisted TO-BE recommendations were returned. Use Generate recommendations if the backend has enough evidence."
          />
        ) : (
          <ul className="space-y-4">
            {rows.map((rec) => (
              <li key={rec.id} className="rounded-lg border border-slate-200 p-4">
                <div className="flex flex-wrap justify-between gap-2">
                  <Link className="link font-semibold" to={`/recommendations/${rec.id}`}>
                    {rec.title}
                  </Link>
                  <span className="text-sm">{rec.status}</span>
                </div>
                <p className="mt-1 text-sm text-slate-600">{rec.description}</p>
                <p className="mt-1 text-xs text-slate-500">
                  {rec.recommendation_type}
                  {rec.confidence != null ? ` · confidence ${rec.confidence}` : ''}
                  {rec.expected_benefit ? ` · ${rec.expected_benefit}` : ''}
                </p>
                <div className="mt-2">
                  <p className="text-xs uppercase text-slate-500">Evidence</p>
                  <EvidenceList items={rec.evidence} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  )
}
