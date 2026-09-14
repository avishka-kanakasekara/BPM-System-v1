import { FormEvent, useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { failException, getException, getProcess, retryException, resolveException } from '../services/apiClient'
import type { ExceptionRecord, ProcessRecord } from '../types/api'
import { useAuth } from '../auth/AuthContext'
import { Alert, EmptyState, ExceptionStatusBadge, PageHeader, Panel, Skeleton } from '../components/ui/primitives'
import { canGovern, formatDateTime } from '../components/process-cockpit/helpers'
import EvidenceList from '../components/operations/EvidenceList'
import { isExceptionActionable, operationsErrorMessage } from '../lib/operations'

function detailLines(details: Record<string, unknown> | undefined): string[] {
  if (!details) return []
  return Object.entries(details).map(([key, value]) => {
    if (Array.isArray(value)) return `${key}: ${value.map(String).join(', ')}`
    if (value && typeof value === 'object') return `${key}: ${JSON.stringify(value)}`
    return `${key}: ${String(value)}`
  })
}

export default function ExceptionDetailPage() {
  const { exceptionId = '' } = useParams()
  const { user } = useAuth()
  const governor = canGovern(user?.role)
  const [row, setRow] = useState<ExceptionRecord | null>(null)
  const [process, setProcess] = useState<ProcessRecord | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!exceptionId) return
    setLoading(true)
    setError(null)
    try {
      const record = await getException(exceptionId)
      setRow(record)
      if (record.process_id) {
        try {
          setProcess(await getProcess(record.process_id))
        } catch {
          setProcess(null)
        }
      } else {
        setProcess(null)
      }
    } catch (err) {
      setRow(null)
      setError(operationsErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [exceptionId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function runAction(kind: 'resolve' | 'retry' | 'fail') {
    if (!row) return
    if ((kind === 'resolve' || kind === 'fail') && !notes.trim()) {
      setError('Resolution notes are required for resolve and fail.')
      return
    }
    setBusy(kind)
    setError(null)
    setNotice(null)
    try {
      const result =
        kind === 'resolve'
          ? await resolveException(row.id, notes.trim())
          : kind === 'fail'
            ? await failException(row.id, notes.trim())
            : await retryException(row.id, notes.trim() || undefined)
      setRow(result.exception)
      setNotice(`Exception ${kind} completed. Process state is not changed automatically by this screen.`)
      if (result.exception.process_id) {
        try {
          setProcess(await getProcess(result.exception.process_id))
        } catch {
          /* process refresh is best-effort */
        }
      }
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
        <Link to="/exceptions" className="text-sm font-medium text-slate-500">
          ← Exceptions
        </Link>
        {error ? <Alert tone="error">{error}</Alert> : <EmptyState title="Exception not found" body="No exception record was returned." />}
      </div>
    )
  }

  const details = detailLines(row.details)
  const showActions = governor && isExceptionActionable(row.status)

  return (
    <div className="space-y-6">
      <Link to="/exceptions" className="text-sm font-medium text-slate-500">
        ← Exceptions
      </Link>
      <PageHeader
        title={row.title || row.exception_code || 'Exception'}
        description={`${row.exception_code || row.type} · ${row.status}`}
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      {notice ? <Alert tone="info">{notice}</Alert> : null}

      <Panel title="Exception summary">
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase text-slate-500">Code</dt>
            <dd>{row.exception_code || row.type}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Status</dt>
            <dd>
              <ExceptionStatusBadge status={row.status} />
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Severity</dt>
            <dd>{row.severity}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Created</dt>
            <dd>{formatDateTime(row.created_at)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Updated</dt>
            <dd>{formatDateTime(row.updated_at)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Process</dt>
            <dd>
              {row.process_id ? (
                <Link className="link" to={`/processes/${row.process_id}`}>
                  {process?.name || row.process_id}
                </Link>
              ) : (
                '—'
              )}
            </dd>
          </div>
        </dl>
      </Panel>

      <Panel title="Cause and details">
        <p className="text-sm">{row.description}</p>
        {details.length > 0 ? (
          <ul className="mt-3 list-disc pl-4 text-sm">
            {details.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        ) : null}
        <div className="mt-3 text-sm">
          <p className="text-xs uppercase text-slate-500">Evidence</p>
          <EvidenceList items={row.evidence_refs} />
        </div>
        <p className="mt-3 break-all font-mono text-xs text-slate-500">
          Plan {row.workflow_plan_id || '—'} · step {row.workflow_step_id || '—'}
        </p>
        {row.source_operation ? (
          <p className="mt-1 text-xs text-slate-500">
            Source {row.source_agent || '—'} / {row.source_operation}
          </p>
        ) : null}
      </Panel>

      <Panel title="Process context">
        {process ? (
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-xs uppercase text-slate-500">Stage</dt>
              <dd>{process.current_stage}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-slate-500">Status</dt>
              <dd>{process.status}</dd>
            </div>
          </dl>
        ) : (
          <p className="text-sm text-slate-500">Process context unavailable.</p>
        )}
      </Panel>

      <Panel title="Resolution history">
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase text-slate-500">Resolution notes</dt>
            <dd>{row.resolution_notes || '—'}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Resolved at</dt>
            <dd>{formatDateTime(row.resolved_at)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-slate-500">Resolved by</dt>
            <dd className="font-mono text-xs">{row.resolved_by_employee_id || '—'}</dd>
          </div>
        </dl>
      </Panel>

      {showActions ? (
        <Panel title="Actions">
          <form
            className="space-y-3"
            onSubmit={(e: FormEvent) => {
              e.preventDefault()
            }}
          >
            <label className="block text-sm">
              Notes
              <textarea
                className="textarea textarea-bordered mt-1 w-full"
                rows={3}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Required for resolve and fail"
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn btn-sm" disabled={busy !== null} onClick={() => void runAction('resolve')}>
                {busy === 'resolve' ? 'Resolving…' : 'Resolve'}
              </button>
              <button type="button" className="btn btn-sm btn-ghost" disabled={busy !== null} onClick={() => void runAction('retry')}>
                {busy === 'retry' ? 'Retrying…' : 'Retry'}
              </button>
              <button type="button" className="btn btn-sm btn-outline" disabled={busy !== null} onClick={() => void runAction('fail')}>
                {busy === 'fail' ? 'Failing…' : 'Fail'}
              </button>
            </div>
            <p className="text-xs text-slate-500">
              These calls are explicit. Retry is not automatic and this page does not recover or complete the process by itself.
            </p>
          </form>
        </Panel>
      ) : (
        <p className="text-sm text-slate-500">
          Exception actions are limited to authorized approver or admin users when the backend permits them.
        </p>
      )}
    </div>
  )
}
