import { FormEvent, useCallback, useEffect, useState } from 'react'
import {
  ApprovalDecisionResponse,
  ApprovalRecord,
  decideApproval,
  listApprovals,
} from '../../services/apiClient'

function apiErrorMessage(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  if (typeof detail === 'string') {
    return detail
  }
  return (err as Error).message || 'Request failed'
}

function ApprovalView() {
  const [items, setItems] = useState<ApprovalRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [lastDecision, setLastDecision] = useState<ApprovalDecisionResponse | null>(null)
  const [comments, setComments] = useState<Record<string, string>>({})

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const pending = await listApprovals('PENDING')
      setItems(pending)
    } catch (err) {
      setError(apiErrorMessage(err))
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function onDecide(
    event: FormEvent,
    approval: ApprovalRecord,
    decision: 'approve' | 'reject',
  ) {
    event.preventDefault()
    setBusyId(approval.id)
    setError(null)
    setLastDecision(null)
    try {
      const result = await decideApproval(
        approval.id,
        decision,
        comments[approval.id]?.trim() || undefined,
      )
      setLastDecision(result)
      await refresh()
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="mx-auto max-w-5xl p-8">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Approvals</h1>
          <p className="mt-1 text-gray-600">
            Pending human gates from Agent 4. Approving continues the process into
            Agent 2 execution; rejecting moves it to EXCEPTION without executing.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refresh()}
          className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          disabled={loading || busyId !== null}
        >
          Refresh
        </button>
      </div>

      {error ? (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      ) : null}

      {lastDecision ? (
        <div className="mb-4 rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          <p>
            Decision <span className="font-semibold">{lastDecision.decision}</span> recorded
            for process {lastDecision.approval.process_id}.
          </p>
          {lastDecision.workflow ? (
            <p className="mt-1">
              Workflow stage: <span className="font-semibold">{lastDecision.workflow.current_stage}</span>
              {' — '}
              {lastDecision.workflow.message}
            </p>
          ) : null}
        </div>
      ) : null}

      {loading ? (
        <p className="text-sm text-gray-500">Loading pending approvals…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-gray-500">No pending approvals.</p>
      ) : (
        <ul className="space-y-4">
          {items.map((approval) => (
            <li
              key={approval.id}
              className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="text-lg font-semibold text-gray-900">{approval.reason}</h2>
                <span className="text-xs font-medium uppercase tracking-wide text-amber-700">
                  {approval.risk_level} · {approval.status}
                </span>
              </div>
              <dl className="mt-3 grid gap-2 text-sm text-gray-600 sm:grid-cols-2">
                <div>
                  <dt className="font-medium text-gray-500">Approval ID</dt>
                  <dd className="font-mono text-xs">{approval.id}</dd>
                </div>
                <div>
                  <dt className="font-medium text-gray-500">Process ID</dt>
                  <dd className="font-mono text-xs">{approval.process_id}</dd>
                </div>
                <div>
                  <dt className="font-medium text-gray-500">Created</dt>
                  <dd>{new Date(approval.created_at).toLocaleString()}</dd>
                </div>
              </dl>
              <form className="mt-4 space-y-3">
                <label className="block text-sm text-gray-700">
                  Comments
                  <textarea
                    className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    rows={2}
                    value={comments[approval.id] ?? ''}
                    onChange={(event) =>
                      setComments((current) => ({
                        ...current,
                        [approval.id]: event.target.value,
                      }))
                    }
                    disabled={busyId === approval.id}
                  />
                </label>
                <div className="flex flex-wrap gap-3">
                  <button
                    type="submit"
                    onClick={(event) => void onDecide(event, approval, 'approve')}
                    disabled={busyId !== null}
                    className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {busyId === approval.id ? 'Working…' : 'Approve & execute'}
                  </button>
                  <button
                    type="submit"
                    onClick={(event) => void onDecide(event, approval, 'reject')}
                    disabled={busyId !== null}
                    className="rounded-md border border-red-300 bg-white px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
                  >
                    Reject
                  </button>
                </div>
              </form>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default ApprovalView
