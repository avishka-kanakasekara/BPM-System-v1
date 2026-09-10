import { useEffect, useState } from 'react'
import {
  apiErrorMessage,
  decideOptimization,
  listOptimizationRecommendations,
  type OptimizationRecommendation,
} from '../../services/apiClient'
import { useAuth } from '../../auth/AuthContext'
import {
  Alert,
  Badge,
  EmptyState,
  PageHeader,
  Panel,
  Spinner,
} from '../../components/ui/primitives'

export default function Agent2RecommendationsPage() {
  const { user } = useAuth()
  const [rows, setRows] = useState<OptimizationRecommendation[]>([])
  const [processId, setProcessId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)

  async function refresh() {
    setLoading(true)
    try {
      const data = await listOptimizationRecommendations(processId || undefined)
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

  async function decide(id: string, decision: 'approve' | 'reject') {
    const userId = user?.id || user?.email || 'ui-user'
    setBusyId(id)
    setMessage(null)
    try {
      await decideOptimization(id, decision, userId)
      setMessage(`Recommendation ${decision}d`)
      await refresh()
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Agent 2 — Optimizations"
        description="Govern optimization recommendations. Approve or reject before applying operational changes."
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      {message ? <Alert tone="success">{message}</Alert> : null}

      <Panel title="Filter">
        <div className="flex flex-wrap gap-3">
          <input
            placeholder="Process ID (optional)"
            value={processId}
            onChange={(e) => setProcessId(e.target.value)}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            type="button"
            onClick={() => void refresh()}
            className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white"
          >
            Refresh
          </button>
        </div>
      </Panel>

      <Panel>
        {loading ? (
          <Spinner />
        ) : rows.length === 0 ? (
          <EmptyState
            title="No recommendations"
            body="Bottleneck and anomaly detectors publish suggestions after execution analytics run."
          />
        ) : (
          <ul className="space-y-4">
            {rows.map((rec) => (
              <li key={rec.id} className="rounded-lg border border-slate-200 p-4">
                <div className="flex flex-wrap gap-2">
                  <Badge tone="accent">{rec.recommendation_type || 'optimization'}</Badge>
                  <Badge
                    tone={
                      rec.status === 'APPROVED'
                        ? 'good'
                        : rec.status === 'REJECTED'
                          ? 'bad'
                          : 'warn'
                    }
                  >
                    {rec.status}
                  </Badge>
                  {rec.risk ? <Badge tone="warn">risk {rec.risk}</Badge> : null}
                </div>
                <p className="mt-2 font-medium text-slate-900">{rec.problem || 'Recommendation'}</p>
                {rec.root_cause ? (
                  <p className="mt-1 text-sm text-slate-600">Root cause: {rec.root_cause}</p>
                ) : null}
                <p className="mt-2 text-xs text-slate-500">
                  process {rec.process_id}
                  {rec.improvement_percent != null
                    ? ` · +${rec.improvement_percent}% predicted`
                    : ''}
                  {rec.confidence != null ? ` · confidence ${rec.confidence}` : ''}
                </p>
                {rec.status === 'PENDING' || rec.status === 'PENDING_APPROVAL' ? (
                  <div className="mt-3 flex gap-2">
                    <button
                      type="button"
                      disabled={busyId === rec.id}
                      onClick={() => void decide(rec.id, 'approve')}
                      className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      disabled={busyId === rec.id}
                      onClick={() => void decide(rec.id, 'reject')}
                      className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                    >
                      Reject
                    </button>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  )
}
