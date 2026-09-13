import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  apiErrorMessage,
  getExecutionReceiptDetail,
  retryAgent2Execution,
  type ExecutionReceiptDetail,
} from '../../services/apiClient'
import {
  Alert,
  Badge,
  EmptyState,
  PageHeader,
  Panel,
  Spinner,
} from '../../components/ui/primitives'

function toneForStatus(status: string): 'good' | 'bad' | 'neutral' | 'warn' {
  const s = status.toUpperCase()
  if (s === 'SUCCESS') return 'good'
  if (s === 'FAILED' || s === 'BLOCKED') return 'bad'
  if (s === 'RETRYING') return 'warn'
  return 'neutral'
}

export default function Agent2ExecutionDetailPage() {
  const { receiptId = '' } = useParams()
  const [detail, setDetail] = useState<ExecutionReceiptDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [retrying, setRetrying] = useState(false)

  async function load() {
    if (!receiptId) return
    setLoading(true)
    try {
      const data = await getExecutionReceiptDetail(receiptId)
      setDetail(data)
      setError(null)
    } catch (err) {
      setError(apiErrorMessage(err))
      setDetail(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [receiptId])

  async function handleRetry() {
    if (!detail) return
    setRetrying(true)
    try {
      const result = await retryAgent2Execution(receiptId, {
        process_id: detail.process_id,
        task_id: detail.task_id,
        tool_name: detail.tool_name,
        parameters: (detail.result as Record<string, unknown>) || {},
      })
      setDetail(result)
      setError(null)
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setRetrying(false)
    }
  }

  const status = detail?.receipt_status || detail?.status || ''

  return (
    <div className="space-y-6">
      <PageHeader
        title="Execution detail"
        description="Full receipt, authorization, scores, and audit trail for one Agent 2 run."
        actions={
          <Link to="/agent2/receipts" className="text-sm text-indigo-600 hover:underline">
            ← History
          </Link>
        }
      />
      {error ? <Alert tone="error">{error}</Alert> : null}

      {loading ? (
        <Spinner />
      ) : !detail ? (
        <EmptyState title="Receipt not found" body="This execution may not be persisted yet." />
      ) : (
        <>
          <Panel title="Summary">
            <div className="flex flex-wrap items-center gap-3">
              <Badge tone={toneForStatus(status)}>{status}</Badge>
              <span className="font-mono text-sm text-slate-600">
                {detail.execution_id || detail.id}
              </span>
              {status === 'FAILED' ? (
                <button
                  type="button"
                  disabled={retrying}
                  onClick={() => void handleRetry()}
                  className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
                >
                  {retrying ? 'Retrying…' : 'Retry'}
                </button>
              ) : null}
            </div>
            <dl className="mt-4 grid gap-3 sm:grid-cols-2 text-sm">
              <div>
                <dt className="text-slate-500">Tool</dt>
                <dd className="font-medium">{detail.tool_name}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Latency</dt>
                <dd className="font-medium">{detail.latency_ms ?? '—'} ms</dd>
              </div>
              <div>
                <dt className="text-slate-500">Process</dt>
                <dd className="font-mono text-xs">{detail.process_id}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Task</dt>
                <dd className="font-mono text-xs">{detail.task_id}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Attempt</dt>
                <dd>{detail.attempt ?? detail.attempt_number}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Idempotency key</dt>
                <dd className="font-mono text-xs break-all">{detail.idempotency_key}</dd>
              </div>
            </dl>
          </Panel>

          <Panel title="Authorization">
            <dl className="grid gap-2 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-slate-500">Agent 4 authorized</dt>
                <dd>
                  {detail.authorization?.agent4_authorized ? 'Yes' : 'No / read-only path'}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Tool Guard</dt>
                <dd>{detail.authorization?.tool_guard || '—'}</dd>
              </div>
            </dl>
          </Panel>

          <Panel title="Execution timeline">
            <ol className="space-y-2 border-l-2 border-slate-200 pl-4 text-sm">
              {[
                ['AUTHORIZED', 'Agent 4 stage gate passed'],
                ['PLANNED', (detail as Record<string, unknown>).execution_explanation
                  ? String(((detail as Record<string, unknown>).execution_explanation as Record<string, string>)?.plan_summary || '').slice(0, 120)
                  : 'Cognitive pipeline planned tool execution'],
                ['EXECUTING', detail.started_at || detail.created_at],
                [status, detail.completed_at || '—'],
              ].map(([stage, note]) => (
                <li key={String(stage)}>
                  <span className="font-medium">{stage}</span>
                  <span className="ml-2 text-slate-500">{note || '—'}</span>
                </li>
              ))}
            </ol>
          </Panel>

          {detail.error_message ? (
            <Panel title="Error">
              <p className="text-sm text-red-700">{detail.error_message}</p>
              {detail.error_type ? (
                <p className="mt-1 font-mono text-xs text-slate-500">{detail.error_type}</p>
              ) : null}
            </Panel>
          ) : null}

          <Panel title="Result payload">
            <pre className="max-h-96 overflow-auto rounded bg-slate-50 p-3 text-xs">
              {JSON.stringify(detail.result ?? {}, null, 2)}
            </pre>
          </Panel>
        </>
      )}
    </div>
  )
}
