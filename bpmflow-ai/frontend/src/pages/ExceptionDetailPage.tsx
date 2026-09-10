import { useCallback, useEffect, useId, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  apiErrorMessage,
  failException,
  getException,
  getProcess,
  listAuditLogs,
  resolveException,
  retryException,
  type AuditLogRecord,
  type ExceptionRecord,
  type ProcessRecord,
} from '../services/apiClient'
import {
  Alert,
  EmptyState,
  ExceptionStatusBadge,
  PageHeader,
  Panel,
  RiskBadge,
} from '../components/ui/primitives'
import { formatExceptionStatus, formatProcessStage } from '../lib/statusPresentation'

function exceptionsErrorMessage(err: unknown): string {
  const status = (err as { response?: { status?: number } })?.response?.status
  if (status === 401) return 'Your session has expired. Please sign in again.'
  if (status === 403) return "You don't have permission to perform this action."
  if (status === 404) return 'This exception could not be found.'
  if (status === 409) return 'This action is not available for the current exception state.'
  if (status === 503) return 'The exception service is temporarily unavailable.'
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

function formatExceptionType(type: string | null | undefined): string {
  if (!type) return 'Exception'
  return type
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatAuditAction(action: string): string {
  const map: Record<string, string> = {
    EXCEPTION_CREATED: 'Exception created',
    EXCEPTION_OPENED: 'Exception created',
    CREATED: 'Exception created',
    RETRY: 'Exception retried',
    EXCEPTION_RETRIED: 'Exception retried',
    RESOLVE: 'Exception resolved',
    EXCEPTION_RESOLVED: 'Exception resolved',
    FAIL: 'Exception closed without recovery',
    EXCEPTION_FAILED: 'Exception closed without recovery',
    IGNORED: 'Exception ignored',
  }
  const key = action.toUpperCase()
  if (map[key]) return map[key]
  return action
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-slate-200/70 ${className}`} />
}

type ConfirmKind = 'retry' | 'ignore' | null

const LIFECYCLE_ACTIVE = ['open', 'in_progress', 'resolved'] as const

export default function ExceptionDetailPage() {
  const { exceptionId = '' } = useParams()
  const formId = useId()
  const notesId = `${formId}-notes`
  const modalTitleId = `${formId}-confirm-title`

  const [exception, setException] = useState<ExceptionRecord | null>(null)
  const [process, setProcess] = useState<ProcessRecord | null>(null)
  const [audit, setAudit] = useState<AuditLogRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [notes, setNotes] = useState('')
  const [fieldError, setFieldError] = useState<string | null>(null)
  const [busy, setBusy] = useState<'resolve' | 'retry' | 'ignore' | null>(null)
  const [confirm, setConfirm] = useState<ConfirmKind>(null)

  const refresh = useCallback(async () => {
    if (!exceptionId) return
    setLoading(true)
    setError(null)
    try {
      const row = await getException(exceptionId)
      setException(row)

      if (row.process_id) {
        try {
          const proc = await getProcess(row.process_id)
          setProcess(proc)
        } catch {
          setProcess(null)
        }

        const logs = await listAuditLogs({
          entity_type: 'exception',
          entity_id: exceptionId,
          limit: 20,
        }).catch(async () => {
          return listAuditLogs({
            entity_type: 'process',
            entity_id: row.process_id!,
            limit: 20,
          }).catch(() => [] as AuditLogRecord[])
        })
        setAudit(logs)
      } else {
        setProcess(null)
        setAudit([])
      }
    } catch (err) {
      setError(exceptionsErrorMessage(err))
      setException(null)
    } finally {
      setLoading(false)
    }
  }, [exceptionId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const isActive =
    exception?.status === 'open' || exception?.status === 'in_progress'
  const isTerminal =
    exception?.status === 'resolved' || exception?.status === 'ignored'

  const lifecycleSteps = useMemo(() => {
    if (!exception) return []
    if (exception.status === 'ignored') {
      return [
        { key: 'open', label: 'Open' },
        { key: 'ignored', label: 'Ignored' },
      ]
    }
    return LIFECYCLE_ACTIVE.map((key) => ({
      key,
      label:
        key === 'open' ? 'Open' : key === 'in_progress' ? 'In Progress' : 'Resolved',
    }))
  }, [exception])

  async function onResolve() {
    if (!exceptionId || busy) return
    const text = notes.trim()
    if (!text) {
      setFieldError('Resolution notes are required to resolve this exception.')
      return
    }
    setFieldError(null)
    setBusy('resolve')
    setError(null)
    setNotice(null)
    try {
      await resolveException(exceptionId, text)
      setNotice('Exception marked as resolved.')
      setNotes('')
      await refresh()
    } catch (err) {
      setError(exceptionsErrorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  async function onRetry() {
    if (!exceptionId || busy) return
    setConfirm(null)
    setBusy('retry')
    setError(null)
    setNotice(null)
    try {
      await retryException(exceptionId, notes.trim() || undefined)
      setNotice(
        'Retry submitted. The process stage is determined by the backend recovery path.',
      )
      await refresh()
    } catch (err) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 409) {
        setError('Retry is no longer available for this exception.')
      } else {
        setError(exceptionsErrorMessage(err))
      }
    } finally {
      setBusy(null)
    }
  }

  async function onIgnore() {
    if (!exceptionId || busy) return
    const text = notes.trim()
    if (!text) {
      setFieldError('Notes are required to close this exception without recovery.')
      setConfirm(null)
      return
    }
    setFieldError(null)
    setConfirm(null)
    setBusy('ignore')
    setError(null)
    setNotice(null)
    try {
      await failException(exceptionId, text)
      setNotice('Exception closed without recovery (Ignored).')
      setNotes('')
      await refresh()
    } catch (err) {
      setError(exceptionsErrorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  if (loading && !exception) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }

  if (!exception && error) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <Link to="/exceptions" className="text-sm font-medium text-slate-500 hover:text-slate-800">
          ← Back to Exceptions
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

  if (!exception) return null

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <Link to="/exceptions" className="text-sm font-medium text-slate-500 hover:text-slate-800">
          ← Back to Exceptions
        </Link>
        <div className="mt-3">
          <PageHeader
            title={formatExceptionType(exception.type)}
            description="Review the failure and choose a recovery action. The backend determines the resulting process stage."
            actions={<ExceptionStatusBadge status={exception.status} />}
          />
        </div>
      </div>

      {error ? <Alert tone="error">{error}</Alert> : null}
      {notice ? <Alert tone="success">{notice}</Alert> : null}

      <Panel title="Lifecycle">
        <ol className="flex flex-wrap items-center gap-2 text-sm">
          {lifecycleSteps.map((step, idx) => {
            const current = exception.status === step.key
            const past =
              (exception.status === 'in_progress' && step.key === 'open') ||
              (exception.status === 'resolved' &&
                (step.key === 'open' || step.key === 'in_progress')) ||
              (exception.status === 'ignored' && step.key === 'open')
            return (
              <li key={step.key} className="flex items-center gap-2">
                <span
                  className={[
                    'rounded-md px-2.5 py-1 text-xs font-medium',
                    current
                      ? 'bg-slate-900 text-white'
                      : past
                        ? 'bg-slate-200 text-slate-700'
                        : 'bg-slate-100 text-slate-400',
                  ].join(' ')}
                >
                  {step.label}
                </span>
                {idx < lifecycleSteps.length - 1 ? (
                  <span className="text-slate-300" aria-hidden>
                    →
                  </span>
                ) : null}
              </li>
            )
          })}
        </ol>
      </Panel>

      <Panel title="Exception">
        <dl className="grid gap-4 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Type</dt>
            <dd className="mt-1 font-medium text-slate-900">
              {formatExceptionType(exception.type)}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Severity</dt>
            <dd className="mt-1">
              <RiskBadge level={exception.severity} />
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Status</dt>
            <dd className="mt-1">
              <ExceptionStatusBadge status={exception.status} />
              <span className="sr-only">{formatExceptionStatus(exception.status)}</span>
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Created</dt>
            <dd className="mt-1 text-slate-800">{formatDateTime(exception.created_at)}</dd>
          </div>
          {exception.resolved_at ? (
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Resolved</dt>
              <dd className="mt-1 text-slate-800">{formatDateTime(exception.resolved_at)}</dd>
            </div>
          ) : null}
          {exception.assigned_to ? (
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Assigned To</dt>
              <dd className="mt-1 break-all font-mono text-xs text-slate-700">
                {exception.assigned_to}
              </dd>
            </div>
          ) : null}
          {exception.task_id ? (
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Task ID</dt>
              <dd className="mt-1 break-all font-mono text-xs text-slate-700">
                {exception.task_id}
              </dd>
            </div>
          ) : null}
          <div className="sm:col-span-2">
            <dt className="text-xs uppercase tracking-wide text-slate-500">Description</dt>
            <dd className="mt-1 text-slate-800">{exception.description}</dd>
          </div>
          {exception.resolution_notes ? (
            <div className="sm:col-span-2">
              <dt className="text-xs uppercase tracking-wide text-slate-500">Resolution Notes</dt>
              <dd className="mt-1 whitespace-pre-wrap text-slate-800">
                {exception.resolution_notes}
              </dd>
            </div>
          ) : null}
        </dl>
      </Panel>

      <Panel title="Process context">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            {exception.process_id ? (
              <>
                <p className="font-medium text-slate-900">
                  {process?.name || `Process ${exception.process_id.slice(0, 8)}…`}
                </p>
                <p className="mt-1 font-mono text-xs text-slate-500">{exception.process_id}</p>
                {process ? (
                  <p className="mt-2 text-sm text-slate-600">
                    Current stage: {formatProcessStage(process.current_stage)}
                  </p>
                ) : null}
              </>
            ) : (
              <p className="text-sm text-slate-500">No process is linked to this exception.</p>
            )}
          </div>
          {exception.process_id ? (
            <Link
              to={`/processes/${exception.process_id}`}
              className="btn btn-ghost btn-sm"
            >
              View Process
            </Link>
          ) : null}
        </div>
      </Panel>

      {isActive ? (
        <Panel title="Recovery">
          <div className="space-y-4 text-sm text-slate-600">
            <div className="rounded-lg border border-slate-100 bg-slate-50/70 px-4 py-3">
              <p className="font-medium text-slate-800">Resolve</p>
              <p className="mt-1">
                Mark this exception as resolved after the issue has been handled.
              </p>
            </div>
            <div className="rounded-lg border border-slate-100 bg-slate-50/70 px-4 py-3">
              <p className="font-medium text-slate-800">Retry</p>
              <p className="mt-1">
                Retry the recovery path for this exception. The backend controls whether the process
                returns to discovery — the frontend does not change stages itself.
              </p>
            </div>
            <div className="rounded-lg border border-slate-100 bg-slate-50/70 px-4 py-3">
              <p className="font-medium text-slate-800">Close Without Recovery</p>
              <p className="mt-1">
                Close this exception without recovery. The backend records it as Ignored.
              </p>
            </div>
          </div>

          <label htmlFor={notesId} className="mt-5 block text-sm">
            <span className="font-medium text-slate-800">
              Notes <span className="font-normal text-slate-400">(required for resolve / close)</span>
            </span>
            <p className="mt-0.5 text-xs text-slate-500">
              What was done to resolve this issue, or why it is being closed?
            </p>
            <textarea
              id={notesId}
              rows={3}
              value={notes}
              onChange={(e) => {
                setNotes(e.target.value)
                if (fieldError) setFieldError(null)
              }}
              disabled={busy !== null}
              placeholder="Describe the recovery action or reason for closing"
              className="mt-1.5 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-400 disabled:opacity-60"
            />
            {fieldError ? (
              <p className="mt-1.5 text-sm text-rose-700" role="alert">
                {fieldError}
              </p>
            ) : null}
          </label>

          <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={busy !== null}
              onClick={() => void onResolve()}
            >
              {busy === 'resolve' ? 'Resolving...' : 'Resolve Exception'}
            </button>
            <button
              type="button"
              className="btn btn-outline btn-sm"
              disabled={busy !== null}
              onClick={() => setConfirm('retry')}
            >
              {busy === 'retry' ? 'Retrying...' : 'Retry'}
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={busy !== null}
              onClick={() => setConfirm('ignore')}
            >
              {busy === 'ignore' ? 'Closing...' : 'Close Without Recovery'}
            </button>
          </div>
        </Panel>
      ) : null}

      {isTerminal ? (
        <Panel title="Recovery">
          <p className="text-sm text-slate-600">
            This exception is{' '}
            <span className="font-medium text-slate-800">
              {formatExceptionStatus(exception.status)}
            </span>
            . Further recovery actions are not available.
          </p>
          {exception.status === 'ignored' ? (
            <p className="mt-2 text-sm text-slate-500">
              Closed without recovery. Retry and resolve are not available.
            </p>
          ) : null}
        </Panel>
      ) : null}

      <Panel title="Exception History">
        {audit.length === 0 ? (
          <EmptyState
            title="No history available"
            body="Audit events for this exception will appear here when available."
          />
        ) : (
          <ol className="space-y-0">
            {audit.slice(0, 12).map((log, idx) => (
              <li key={log.id} className="flex gap-3">
                <div className="flex w-4 flex-col items-center">
                  <span className="mt-1.5 h-2 w-2 rounded-full bg-slate-400" />
                  {idx < Math.min(audit.length, 12) - 1 ? (
                    <span className="my-1 w-px flex-1 bg-slate-200" aria-hidden />
                  ) : null}
                </div>
                <div className="min-w-0 pb-4">
                  <p className="text-sm font-medium text-slate-800">
                    {formatAuditAction(log.action)}
                  </p>
                  <p className="text-xs text-slate-500">{formatDateTime(log.timestamp)}</p>
                </div>
              </li>
            ))}
          </ol>
        )}
      </Panel>

      {confirm ? (
        <div className="modal modal-open">
          <div className="modal-box" role="dialog" aria-modal="true" aria-labelledby={modalTitleId}>
            <h3 id={modalTitleId} className="text-lg font-semibold text-slate-900">
              {confirm === 'retry' ? 'Retry this exception?' : 'Close this exception without recovery?'}
            </h3>
            <p className="mt-2 text-sm text-slate-600">
              {confirm === 'retry'
                ? 'This will attempt the existing recovery path. The backend decides whether the process returns to discovery — the frontend does not change stages itself.'
                : 'The exception will be recorded as Ignored. This does not delete the record.'}
            </p>
            <div className="modal-action flex-col gap-2 sm:flex-row">
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={busy !== null}
                onClick={() => setConfirm(null)}
              >
                Cancel
              </button>
              {confirm === 'retry' ? (
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={busy !== null}
                  onClick={() => void onRetry()}
                >
                  {busy === 'retry' ? 'Retrying...' : 'Retry'}
                </button>
              ) : (
                <button
                  type="button"
                  className="btn btn-sm"
                  disabled={busy !== null}
                  onClick={() => void onIgnore()}
                >
                  {busy === 'ignore' ? 'Closing...' : 'Close Without Recovery'}
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
