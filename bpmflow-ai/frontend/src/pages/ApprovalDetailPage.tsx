import { FormEvent, useCallback, useEffect, useId, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  apiErrorMessage,
  decideApproval,
  getApproval,
  getProcess,
  type ApprovalDecisionResponse,
  type ApprovalRecord,
  type ProcessRecord,
} from '../services/apiClient'
import { useAuth } from '../auth/AuthContext'
import {
  Alert,
  ApprovalStatusBadge,
  PageHeader,
  Panel,
  RiskBadge,
} from '../components/ui/primitives'
import { formatApprovalStatus, formatProcessStage } from '../lib/statusPresentation'

function approvalsErrorMessage(err: unknown): string {
  const status = (err as { response?: { status?: number } })?.response?.status
  if (status === 401) return 'Your session has expired. Please sign in again.'
  if (status === 403) return "You don't have permission to make approval decisions."
  if (status === 404) return 'This approval request could not be found.'
  if (status === 409) return 'This approval request has already been decided.'
  if (status === 503) return 'The approval service is temporarily unavailable.'
  return apiErrorMessage(err)
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function canDecideApprovals(role: string | null | undefined): boolean {
  const r = (role || '').toLowerCase()
  return r === 'approver' || r === 'admin'
}

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-slate-200/70 ${className}`} />
}

type ConfirmKind = 'approve' | 'reject' | null

export default function ApprovalDetailPage() {
  const { approvalId = '' } = useParams()
  const { user } = useAuth()
  const formId = useId()
  const commentsId = `${formId}-comments`
  const modalTitleId = `${formId}-confirm-title`

  const [approval, setApproval] = useState<ApprovalRecord | null>(null)
  const [process, setProcess] = useState<ProcessRecord | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [comments, setComments] = useState('')
  const [busy, setBusy] = useState<'approve' | 'reject' | null>(null)
  const [confirm, setConfirm] = useState<ConfirmKind>(null)
  const [lastDecision, setLastDecision] = useState<ApprovalDecisionResponse | null>(null)

  const allowedToDecide = canDecideApprovals(user?.role)

  const refresh = useCallback(async () => {
    if (!approvalId) return
    setLoading(true)
    setError(null)
    try {
      const row = await getApproval(approvalId)
      setApproval(row)
      try {
        const proc = await getProcess(row.process_id)
        setProcess(proc)
      } catch {
        setProcess(null)
      }
    } catch (err) {
      setError(approvalsErrorMessage(err))
      setApproval(null)
    } finally {
      setLoading(false)
    }
  }, [approvalId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const resultingStage = useMemo(() => {
    const stage = lastDecision?.workflow?.current_stage
    return typeof stage === 'string' ? stage : null
  }, [lastDecision])

  async function submitDecision(decision: 'approve' | 'reject') {
    if (!approvalId || busy) return
    setBusy(decision)
    setError(null)
    setNotice(null)
    setConfirm(null)
    try {
      const res = await decideApproval(
        approvalId,
        decision,
        comments.trim() || undefined,
      )
      setLastDecision(res)
      if (decision === 'approve') {
        setNotice(
          'Human decision recorded. Execution may now continue according to the BPMFlow workflow.',
        )
      } else {
        const stage =
          res.workflow && typeof res.workflow.current_stage === 'string'
            ? res.workflow.current_stage
            : null
        if (stage === 'EXCEPTION') {
          setNotice('Process requires attention.')
        } else {
          setNotice('Rejection recorded. The process stage is determined by the backend.')
        }
      }
      await refresh()
    } catch (err) {
      setError(approvalsErrorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  function onDecisionForm(e: FormEvent) {
    e.preventDefault()
  }

  if (loading && !approval) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }

  if (!approval && error) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <Link to="/approvals" className="text-sm font-medium text-slate-500 hover:text-slate-800">
          ← Back to Approvals
        </Link>
        <Alert tone="error">
          <div className="space-y-2">
            <p>{error}</p>
            <button type="button" className="btn btn-ghost btn-xs" onClick={() => void refresh()}>
              Retry
            </button>
          </div>
        </Alert>
      </div>
    )
  }

  if (!approval) return null

  const isPending = approval.status === 'PENDING'
  const processLabel = process?.name || `Process ${approval.process_id.slice(0, 8)}…`

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <Link to="/approvals" className="text-sm font-medium text-slate-500 hover:text-slate-800">
          ← Back to Approvals
        </Link>
        <div className="mt-3">
          <PageHeader
            title="Approval Request"
            description="AI risk assessment informs the decision. A human must authorize before execution continues."
            actions={<ApprovalStatusBadge status={approval.status} />}
          />
        </div>
      </div>

      {error ? <Alert tone="error">{error}</Alert> : null}
      {notice ? <Alert tone={resultingStage === 'EXCEPTION' ? 'warning' : 'success'}>{notice}</Alert> : null}

      <Panel title="Process context">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="font-medium text-slate-900">{processLabel}</p>
            <p className="mt-1 font-mono text-xs text-slate-500">{approval.process_id}</p>
            {process ? (
              <p className="mt-2 text-sm text-slate-600">
                Current stage: {formatProcessStage(process.current_stage)}
              </p>
            ) : null}
          </div>
          <Link to={`/processes/${approval.process_id}`} className="btn btn-ghost btn-sm">
            View Process
          </Link>
        </div>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Requested</dt>
            <dd className="mt-1 text-slate-800">{formatDateTime(approval.created_at)}</dd>
          </div>
          {approval.requested_by ? (
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Requested by</dt>
              <dd className="mt-1 break-all font-mono text-xs text-slate-700">
                {approval.requested_by}
              </dd>
            </div>
          ) : null}
        </dl>
      </Panel>

      <Panel title="AI Risk Assessment">
        <p className="mb-4 text-sm text-slate-500">
          System recommendation only. This is not an authorization.
        </p>
        <dl className="grid gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Risk Level</dt>
            <dd className="mt-1">
              <RiskBadge level={approval.risk_level} />
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">
              AI Recommendation
            </dt>
            <dd className="mt-1 text-sm font-medium text-slate-900">Human Approval Required</dd>
          </div>
        </dl>
        <div className="mt-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Why this requires review
          </p>
          <p className="mt-1 text-sm leading-relaxed text-slate-700">{approval.reason}</p>
        </div>
      </Panel>

      {isPending ? (
        <Panel title="Your Decision">
          {!allowedToDecide ? (
            <Alert tone="info">
              Approval decision requires an authorized approver. You can review this request, but
              Approve and Reject are available only to approver or admin roles. The backend remains
              the security authority.
            </Alert>
          ) : (
            <form className="space-y-4" onSubmit={onDecisionForm}>
              <label htmlFor={commentsId} className="block text-sm">
                <span className="font-medium text-slate-800">
                  Comments <span className="font-normal text-slate-400">(optional)</span>
                </span>
                <textarea
                  id={commentsId}
                  rows={3}
                  value={comments}
                  onChange={(e) => setComments(e.target.value)}
                  disabled={busy !== null}
                  placeholder="Add context for the audit trail"
                  className="mt-1.5 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400 disabled:opacity-60"
                />
              </label>
              <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                <button
                  type="button"
                  className="btn btn-outline btn-sm border-rose-300 text-rose-800 hover:bg-rose-50"
                  disabled={busy !== null}
                  onClick={() => setConfirm('reject')}
                >
                  Reject
                </button>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={busy !== null}
                  onClick={() => setConfirm('approve')}
                >
                  Approve
                </button>
              </div>
            </form>
          )}
        </Panel>
      ) : (
        <Panel
          title={
            approval.status === 'APPROVED'
              ? 'Approved by Human'
              : approval.status === 'REJECTED'
                ? 'Rejected by Human'
                : 'Human Decision'
          }
        >
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Decision</dt>
              <dd className="mt-1 font-medium text-slate-900">
                {formatApprovalStatus(approval.status)}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Decision time</dt>
              <dd className="mt-1 text-slate-800">
                {formatDateTime(approval.decided_at || approval.created_at)}
              </dd>
            </div>
            {approval.approver_id ? (
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Approver</dt>
                <dd className="mt-1 break-all font-mono text-xs text-slate-700">
                  {approval.approver_id}
                </dd>
              </div>
            ) : null}
            {approval.comments ? (
              <div className="sm:col-span-2">
                <dt className="text-xs uppercase tracking-wide text-slate-500">Comments</dt>
                <dd className="mt-1 text-slate-800">{approval.comments}</dd>
              </div>
            ) : null}
            {resultingStage ? (
              <div className="sm:col-span-2">
                <dt className="text-xs uppercase tracking-wide text-slate-500">
                  Resulting process stage
                </dt>
                <dd className="mt-1 text-slate-800">{formatProcessStage(resultingStage)}</dd>
              </div>
            ) : process ? (
              <div className="sm:col-span-2">
                <dt className="text-xs uppercase tracking-wide text-slate-500">Process stage</dt>
                <dd className="mt-1 text-slate-800">
                  {formatProcessStage(process.current_stage)}
                </dd>
              </div>
            ) : null}
          </dl>

          {approval.status === 'APPROVED' ? (
            <p className="mt-4 text-sm text-slate-600">
              Human authorization is recorded. Execution continues only as directed by the BPMFlow
              workflow — approval does not mean execution has completed.
            </p>
          ) : null}

          {approval.status === 'REJECTED' &&
          (process?.current_stage === 'EXCEPTION' || resultingStage === 'EXCEPTION') ? (
            <div className="mt-4">
              <p className="text-sm font-medium text-slate-800">Process requires attention.</p>
              <Link to="/exceptions" className="btn btn-ghost btn-sm mt-2">
                View Exceptions
              </Link>
            </div>
          ) : null}
        </Panel>
      )}

      {/* Confirm dialogs */}
      {confirm ? (
        <div className="modal modal-open">
          <div className="modal-box" role="dialog" aria-modal="true" aria-labelledby={modalTitleId}>
            <h3 id={modalTitleId} className="text-lg font-semibold text-slate-900">
              {confirm === 'approve' ? 'Approve this process?' : 'Reject this approval request?'}
            </h3>
            <p className="mt-2 text-sm text-slate-600">
              {confirm === 'approve'
                ? 'By approving, you authorize the workflow to continue to the next execution stage. This does not mean execution has already completed.'
                : 'Rejecting records a human decision against this request. The resulting process stage is determined by the backend.'}
            </p>
            {confirm === 'reject' && comments.trim() ? (
              <p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700">
                <span className="font-medium">Comments: </span>
                {comments.trim()}
              </p>
            ) : null}
            <div className="modal-action flex-col gap-2 sm:flex-row">
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={busy !== null}
                onClick={() => setConfirm(null)}
              >
                Cancel
              </button>
              {confirm === 'approve' ? (
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={busy !== null}
                  onClick={() => void submitDecision('approve')}
                >
                  {busy === 'approve' ? 'Approving...' : 'Approve Process'}
                </button>
              ) : (
                <button
                  type="button"
                  className="btn btn-sm border-rose-300 bg-rose-600 text-white hover:bg-rose-700"
                  disabled={busy !== null}
                  onClick={() => void submitDecision('reject')}
                >
                  {busy === 'reject' ? 'Rejecting...' : 'Reject Process'}
                </button>
              )}
            </div>
          </div>
          <button
            type="button"
            className="modal-backdrop bg-slate-900/40"
            aria-label="Close confirmation"
            onClick={() => (busy ? undefined : setConfirm(null))}
          />
        </div>
      ) : null}
    </div>
  )
}
