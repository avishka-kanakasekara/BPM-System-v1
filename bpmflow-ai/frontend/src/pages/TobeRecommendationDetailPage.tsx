import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getTobeRecommendation, reviewTobeRecommendation } from '../services/apiClient'
import type { TobeRecommendationRecord } from '../types/api'
import { useAuth } from '../auth/AuthContext'
import { Alert, EmptyState, PageHeader, Panel, Skeleton } from '../components/ui/primitives'
import EvidenceList from '../components/operations/EvidenceList'
import { canGovern, formatDateTime } from '../components/process-cockpit/helpers'
import { operationsErrorMessage } from '../lib/operations'

export default function TobeRecommendationDetailPage() {
  const { recommendationId = '' } = useParams()
  const { user } = useAuth()
  const reviewer = canGovern(user?.role)
  const [row, setRow] = useState<TobeRecommendationRecord | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!recommendationId) return
    setLoading(true)
    setError(null)
    try {
      setRow(await getTobeRecommendation(recommendationId))
    } catch (err) {
      setRow(null)
      setError(operationsErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [recommendationId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function onReview(decision: 'ACCEPTED' | 'REJECTED') {
    if (!row) return
    setBusy(decision)
    setError(null)
    setNotice(null)
    try {
      const updated = await reviewTobeRecommendation(row.id, {
        decision,
        comment: comment.trim() || undefined,
      })
      setRow(updated)
      setNotice(
        `Recommendation ${decision}. This is a governance decision only — no workflow was activated and the process was not modified by this screen.`,
      )
    } catch (err) {
      setError(operationsErrorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  if (loading && !row) {
    return (
      <div aria-busy="true">
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }

  if (!row) {
    return (
      <div className="space-y-4">
        <Link to="/recommendations" className="text-sm font-medium text-slate-500">
          ← TO-BE recommendations
        </Link>
        {error ? <Alert tone="error">{error}</Alert> : <EmptyState title="Recommendation not found" body="No TO-BE recommendation was returned." />}
      </div>
    )
  }

  const reviewable = reviewer && row.status === 'PROPOSED'

  return (
    <div className="space-y-6">
      <Link to={row.process_id ? `/recommendations?process=${row.process_id}` : '/recommendations'} className="text-sm font-medium text-slate-500">
        ← TO-BE recommendations
      </Link>
      <PageHeader title={row.title} description={`TO-BE Process Recommendation · ${row.status}`} />
      {error ? <Alert tone="error">{error}</Alert> : null}
      {notice ? <Alert tone="info">{notice}</Alert> : null}
      <Panel title="Recommendation">
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase text-slate-500">ID</dt>
            <dd className="font-mono text-xs">{row.id}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Type</dt>
            <dd>{row.recommendation_type}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Process</dt>
            <dd>
              {row.process_id ? (
                <Link className="link" to={`/processes/${row.process_id}`}>
                  Open process
                </Link>
              ) : (
                '—'
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Confidence</dt>
            <dd>{row.confidence == null ? '—' : String(row.confidence)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Expected impact</dt>
            <dd>{row.expected_benefit || '—'}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Risk</dt>
            <dd>{row.risk || '—'}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Policy</dt>
            <dd>{row.policy_status || '—'}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Activates workflow</dt>
            <dd>{row.activates_workflow ? 'Yes' : 'No'}</dd>
          </div>
        </dl>
        <div className="mt-4 space-y-2 text-sm">
          <p>
            <span className="text-xs uppercase text-slate-500">AS-IS / current issue</span>
            <br />
            {row.reason}
          </p>
          <p>
            <span className="text-xs uppercase text-slate-500">Proposed improvement</span>
            <br />
            {row.description}
          </p>
        </div>
      </Panel>
      <Panel title="Evidence">
        <EvidenceList items={row.evidence} />
      </Panel>
      <Panel title="Review">
        <p className="text-sm text-slate-600">
          Created {formatDateTime(row.created_at)}
          {row.reviewed_at ? ` · reviewed ${formatDateTime(row.reviewed_at)}` : ''}
        </p>
        {reviewable ? (
          <div className="mt-3 space-y-3">
            <label className="block text-sm">
              Comment (optional)
              <textarea className="textarea textarea-bordered mt-1 w-full" rows={2} value={comment} onChange={(e) => setComment(e.target.value)} />
            </label>
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn btn-primary btn-sm" disabled={busy !== null} onClick={() => void onReview('ACCEPTED')}>
                {busy === 'ACCEPTED' ? 'Accepting…' : 'Accept'}
              </button>
              <button type="button" className="btn btn-outline btn-sm" disabled={busy !== null} onClick={() => void onReview('REJECTED')}>
                {busy === 'REJECTED' ? 'Rejecting…' : 'Reject'}
              </button>
            </div>
            <p className="text-xs text-slate-500">There is no implement-automatically action. Acceptance does not activate a workflow.</p>
          </div>
        ) : (
          <p className="mt-2 text-sm text-slate-500">
            {row.status === 'NOT_ALLOWED'
              ? 'This recommendation is not reviewable.'
              : 'Review is limited to authorized approver or admin users for PROPOSED recommendations.'}
          </p>
        )}
      </Panel>
    </div>
  )
}
