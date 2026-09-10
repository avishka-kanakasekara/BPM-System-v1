import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  apiErrorMessage,
  completeInvoiceMatching,
  executeProcess,
  getDiscoveredProcess,
  getProcess,
  listApprovals,
  listAuditLogs,
  listExceptions,
  listExecutionReceipts,
  planResources,
  riskReview,
  startProcess,
  type AgentMessage,
  type ApprovalRecord,
  type AuditLogRecord,
  type ExceptionRecord,
  type ExecutionReceipt,
  type ProcessDetail,
  type ProcessRecord,
  type ProcessStartResponse,
  type WorkflowResult,
} from '../services/apiClient'
import { useAuth } from '../auth/AuthContext'
import ProcessDiscoveryPanel from '../components/discovery/ProcessDiscoveryPanel'
import {
  Alert,
  EmptyState,
  PageHeader,
  Panel,
  ProcessStageBadge,
  RiskBadge,
} from '../components/ui/primitives'
import {
  formatExceptionStatus,
  formatProcessStage,
} from '../lib/statusPresentation'

const JOURNEY: Array<{ key: string; short: string; label: string }> = [
  { key: 'DRAFT', short: 'Draft', label: 'Draft' },
  { key: 'DISCOVERING', short: 'Discovering', label: 'Discovering' },
  { key: 'RESOURCE_PLANNING', short: 'Resources', label: 'Resource Planning' },
  { key: 'RISK_REVIEW', short: 'Risk', label: 'Risk Review' },
  { key: 'AWAITING_HUMAN_APPROVAL', short: 'Approval', label: 'Human Approval' },
  { key: 'WORKFLOW_EXECUTION', short: 'Execution', label: 'Workflow Execution' },
  { key: 'INVOICE_MATCHING', short: 'Invoice', label: 'Invoice Matching' },
  { key: 'COMPLETED', short: 'Completed', label: 'Completed' },
]

const STAGE_COPY: Record<string, { title: string; body: string }> = {
  DRAFT: {
    title: 'Upload process evidence',
    body: 'Upload documents for this process. Discovery results stay on this process. Then start discovery to advance the stage through Agent 4.',
  },
  DISCOVERING: {
    title: 'Process Discovery',
    body: 'Discovery evidence is available. Continue to resource planning when ready.',
  },
  RESOURCE_PLANNING: {
    title: 'Resource Planning',
    body: 'Workforce and budget requirements are being evaluated. Recommendations are advisory — not approvals.',
  },
  RISK_REVIEW: {
    title: 'Risk Assessment',
    body: 'Risk factors are being assessed before execution. AI assessment does not authorize the work.',
  },
  AWAITING_HUMAN_APPROVAL: {
    title: 'Human Approval Required',
    body: 'AI risk assessment indicates that human authorization is required before execution.',
  },
  WORKFLOW_EXECUTION: {
    title: 'Workflow Execution',
    body: 'Authorized workflow execution is in progress. Actions are controlled and authorized.',
  },
  INVOICE_MATCHING: {
    title: 'Invoice Matching',
    body: 'Execution is complete. The process is now finalizing invoice matching.',
  },
  COMPLETED: {
    title: 'Process Completed',
    body: 'This process has completed successfully.',
  },
  EXCEPTION: {
    title: 'Process requires attention',
    body: 'This process has encountered an exception and requires attention.',
  },
}

function formatProcessType(type: string | null | undefined): string {
  if (!type) return '—'
  return type
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatProcessStatus(status: string | null | undefined): string {
  if (!status) return '—'
  const key = status.toUpperCase()
  if (key === 'ACTIVE' || key === 'IN_PROGRESS' || key === 'RUNNING') return 'Active'
  if (key === 'COMPLETED' || key === 'COMPLETE') return 'Completed'
  if (key === 'DRAFT') return 'Draft'
  if (key === 'EXCEPTION' || key === 'FAILED') return 'Exception'
  if (key === 'CANCELLED' || key === 'CANCELED') return 'Cancelled'
  return formatProcessType(status)
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

function formatAuditAction(action: string): string {
  const map: Record<string, string> = {
    PROCESS_CREATED: 'Process created',
    CREATED: 'Process created',
    STAGE_UPDATED: 'Stage updated',
    START: 'Discovery started',
    PLAN_RESOURCES: 'Resources planned',
    RISK_REVIEW: 'Risk assessed',
    APPROVAL_REQUESTED: 'Approval requested',
    APPROVED: 'Approved by human',
    REJECTED: 'Approval rejected',
    EXECUTE: 'Execution started',
    COMPLETED: 'Process completed',
    EXCEPTION_OPENED: 'Exception opened',
  }
  const key = action.toUpperCase()
  if (map[key]) return map[key]
  return action
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function detailErrorMessage(err: unknown): string {
  const status = (err as { response?: { status?: number } })?.response?.status
  if (status === 401) return 'Your session has expired. Please sign in again.'
  if (status === 403) return "You don't have permission to perform this action."
  if (status === 409) return 'This action cannot be performed at the current process stage.'
  if (status === 503) return 'The BPMFlow AI service is temporarily unavailable.'
  return apiErrorMessage(err)
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function pickString(obj: Record<string, unknown> | null, keys: string[]): string | null {
  if (!obj) return null
  for (const key of keys) {
    const v = obj[key]
    if (typeof v === 'string' && v.trim()) return v
  }
  return null
}

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-slate-200/70 ${className}`} />
}

function journeyIndex(stage: string): number {
  return JOURNEY.findIndex((s) => s.key === stage)
}

function StageStepper({ stage }: { stage: string }) {
  const isException = stage === 'EXCEPTION'
  const currentIdx = journeyIndex(stage)

  return (
    <Panel
      title="Process journey"
      actions={
        isException ? (
          <span className="text-xs font-medium text-rose-700">Exception path</span>
        ) : null
      }
    >
      {isException ? (
        <Alert tone="warning">
          This process is on the exception path and requires attention. The main journey is paused until
          the exception is resolved.
        </Alert>
      ) : null}

      {/* Desktop horizontal */}
      <ol className="hidden items-start justify-between gap-1 md:flex">
        {JOURNEY.map((step, idx) => {
          const done = !isException && currentIdx > idx
          const current = !isException && currentIdx === idx
          return (
            <li key={step.key} className="flex min-w-0 flex-1 flex-col items-center text-center">
              <span
                className={[
                  'flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold',
                  done
                    ? 'bg-slate-900 text-white'
                    : current
                      ? 'bg-sky-600 text-white ring-4 ring-sky-100'
                      : 'bg-slate-100 text-slate-400',
                ].join(' ')}
                aria-current={current ? 'step' : undefined}
              >
                {done ? '✓' : current ? '●' : '○'}
              </span>
              <span
                className={[
                  'mt-2 text-[11px] font-medium leading-tight',
                  current ? 'text-slate-900' : done ? 'text-slate-700' : 'text-slate-400',
                ].join(' ')}
              >
                {step.short}
              </span>
              {idx < JOURNEY.length - 1 ? (
                <span className="sr-only">then</span>
              ) : null}
            </li>
          )
        })}
      </ol>

      {/* Mobile vertical */}
      <ol className="space-y-0 md:hidden">
        {JOURNEY.map((step, idx) => {
          const done = !isException && currentIdx > idx
          const current = !isException && currentIdx === idx
          return (
            <li key={step.key} className="flex gap-3">
              <div className="flex w-8 flex-col items-center">
                <span
                  className={[
                    'flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold',
                    done
                      ? 'bg-slate-900 text-white'
                      : current
                        ? 'bg-sky-600 text-white'
                        : 'bg-slate-100 text-slate-400',
                  ].join(' ')}
                >
                  {done ? '✓' : current ? '●' : '○'}
                </span>
                {idx < JOURNEY.length - 1 ? (
                  <span className="my-1 w-px flex-1 bg-slate-200" aria-hidden />
                ) : null}
              </div>
              <div className={idx < JOURNEY.length - 1 ? 'pb-4 pt-1.5' : 'pt-1.5'}>
                <p
                  className={[
                    'text-sm font-medium',
                    current ? 'text-slate-900' : done ? 'text-slate-700' : 'text-slate-400',
                  ].join(' ')}
                >
                  {step.label}
                </p>
              </div>
            </li>
          )
        })}
      </ol>
    </Panel>
  )
}

export default function ProcessDetailPage() {
  const { processId = '' } = useParams()
  const { user } = useAuth()

  const [process, setProcess] = useState<ProcessRecord | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const [discovery, setDiscovery] = useState<ProcessDetail | null>(null)
  const [latestDiscoveryMessage, setLatestDiscoveryMessage] = useState<AgentMessage | null>(null)
  const [approvals, setApprovals] = useState<ApprovalRecord[]>([])
  const [exceptions, setExceptions] = useState<ExceptionRecord[]>([])
  const [audit, setAudit] = useState<AuditLogRecord[]>([])
  const [receipts, setReceipts] = useState<ExecutionReceipt[]>([])
  const [lastWorkflow, setLastWorkflow] = useState<WorkflowResult | null>(null)
  const [invoiceForm, setInvoiceForm] = useState({
    invoice_number: '',
    amount: '',
    currency: 'USD',
    vendor: '',
    po_reference: '',
    expected_amount: '',
    expected_po_reference: '',
    expected_currency: 'USD',
    expected_vendor: '',
    notes: '',
  })

  const refresh = useCallback(async () => {
    if (!processId) return
    setLoading(true)
    setError(null)
    try {
      const row = await getProcess(processId)
      setProcess(row)

      const [approvalRows, exceptionRows, auditRows, receiptRows] = await Promise.all([
        listApprovals().catch(() => [] as ApprovalRecord[]),
        listExceptions().catch(() => [] as ExceptionRecord[]),
        listAuditLogs({ entity_type: 'process', entity_id: processId, limit: 30 }).catch(
          () => [] as AuditLogRecord[],
        ),
        listExecutionReceipts({ process_id: processId, limit: 50 }).catch(
          () => [] as ExecutionReceipt[],
        ),
      ])

      setApprovals(approvalRows.filter((a) => a.process_id === processId))
      setExceptions(exceptionRows.filter((e) => e.process_id === processId))
      setAudit(auditRows)
      setReceipts(receiptRows)

      try {
        const disc = await getDiscoveredProcess(processId)
        setDiscovery(disc)
      } catch {
        setDiscovery(null)
      }
    } catch (err) {
      setError(detailErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [processId])

  useEffect(() => {
    setLatestDiscoveryMessage(null)
    void refresh()
  }, [refresh])

  const stage = process?.current_stage ?? ''
  const stageMeta = STAGE_COPY[stage] ?? {
    title: formatProcessStage(stage),
    body: 'Review the current process state and available actions.',
  }

  // Prefill invoice expected fields from the PO created during workflow execution.
  useEffect(() => {
    if (stage !== 'INVOICE_MATCHING' || !process?.metadata_json) return
    const meta = process.metadata_json
    const purchase =
      meta.purchase_order && typeof meta.purchase_order === 'object'
        ? (meta.purchase_order as Record<string, unknown>)
        : meta.last_execution && typeof meta.last_execution === 'object'
          ? (meta.last_execution as Record<string, unknown>)
          : null
    if (!purchase) return
    const poRef = String(purchase.po_reference || purchase.po_number || '')
    const amount = purchase.amount != null ? String(purchase.amount) : ''
    const vendor = String(purchase.vendor || purchase.vendor_id || '')
    const currency = String(purchase.currency || 'USD')
    setInvoiceForm((prev) => ({
      ...prev,
      expected_po_reference: prev.expected_po_reference || poRef,
      expected_amount: prev.expected_amount || amount,
      expected_vendor: prev.expected_vendor || vendor,
      expected_currency: prev.expected_currency || currency || 'USD',
      po_reference: prev.po_reference || poRef,
      amount: prev.amount || amount,
      vendor: prev.vendor || vendor,
      currency: prev.currency || currency || 'USD',
    }))
  }, [stage, process?.id, process?.metadata_json])

  const discoveryJson = asRecord(discovery?.process_json)
  const hasDiscoveryResults = Boolean(
    latestDiscoveryMessage ||
      (discoveryJson &&
        ((Array.isArray(discoveryJson.activities) && discoveryJson.activities.length > 0) ||
          (Array.isArray(discoveryJson.rules) && discoveryJson.rules.length > 0) ||
          Object.keys(discoveryJson).length > 0)),
  )

  const pendingApproval = useMemo(
    () => approvals.find((a) => a.status === 'PENDING') ?? null,
    [approvals],
  )
  const decidedApproval = useMemo(() => {
    const decided = approvals.filter((a) => a.status === 'APPROVED' || a.status === 'REJECTED')
    return decided.sort((a, b) => {
      const at = new Date(a.decided_at || a.created_at).getTime()
      const bt = new Date(b.decided_at || b.created_at).getTime()
      return bt - at
    })[0] ?? null
  }, [approvals])

  const openException = useMemo(
    () =>
      exceptions.find((e) => e.status === 'open' || e.status === 'in_progress') ??
      exceptions[0] ??
      null,
    [exceptions],
  )

  const riskFromWorkflow = useMemo(() => {
    const payload = asRecord(lastWorkflow?.agent_response) || asRecord(lastWorkflow)
    const overall =
      pickString(payload, ['overall_risk_level', 'risk_level']) ||
      pendingApproval?.risk_level ||
      decidedApproval?.risk_level ||
      null
    const reason =
      pickString(payload, ['reason', 'summary', 'message']) ||
      pendingApproval?.reason ||
      decidedApproval?.reason ||
      null
    return { overall, reason, humanRequired: Boolean(lastWorkflow?.human_approval_required) }
  }, [lastWorkflow, pendingApproval, decidedApproval])

  const resourcePayload = useMemo(
    () => asRecord(lastWorkflow?.agent_response),
    [lastWorkflow],
  )

  const receiptSummary = useMemo(() => {
    const total = receipts.length
    const successful = receipts.filter((r) => /success|ok|completed/i.test(r.status)).length
    const failed = receipts.filter((r) => /fail|error|blocked/i.test(r.status)).length
    const blocked = receipts.filter((r) => /block/i.test(r.status)).length
    return { total, successful, failed, blocked }
  }, [receipts])

  async function runAction(
    key: string,
    fn: () => Promise<WorkflowResult | ProcessStartResponse>,
  ) {
    if (!processId || busy) return
    setBusy(key)
    setError(null)
    setNotice(null)
    try {
      const res = await fn()
      if ('process' in res && 'success' in res) {
        const startRes = res as ProcessStartResponse
        if (!startRes.success) {
          if (startRes.error_code === 'AGENT_UNAVAILABLE') {
            setNotice(
              'Process discovery is currently unavailable. The process has not been marked as completed.',
            )
          } else {
            setNotice(
              startRes.error_message ||
                startRes.message ||
                'Required service is currently unavailable. The process has not been marked as completed.',
            )
          }
        } else if (startRes.message) {
          setNotice(startRes.message)
        }
      } else {
        const workflowRes = res as WorkflowResult
        setLastWorkflow(workflowRes)
        if (!workflowRes.success) {
          if (workflowRes.error_code === 'AGENT_UNAVAILABLE') {
            setNotice(
              'Required service is currently unavailable. The process has not been marked as completed.',
            )
          } else {
            setNotice(workflowRes.error_message || workflowRes.message || 'Action did not succeed.')
          }
        } else if (workflowRes.message) {
          const ar = asRecord(workflowRes.agent_response)
          const tool = typeof ar.tool_name === 'string' ? ar.tool_name : null
          const receipt =
            typeof ar.receipt_status === 'string' ? ar.receipt_status : null
          const detail =
            tool || receipt
              ? `${workflowRes.message}${tool ? ` · tool ${tool}` : ''}${
                  receipt ? ` · ${receipt}` : ''
                }`
              : workflowRes.message
          setNotice(detail)
        }
      }
      await refresh()
    } catch (err) {
      setError(detailErrorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  async function onStart() {
    await runAction('start', () => startProcess(processId))
  }

  async function onPlanResources() {
    const tenantId = user?.tenant_id
    if (!tenantId) {
      setError('Tenant context is missing from your session. Sign in again and retry.')
      return
    }
    if (!user?.id) {
      setError('Authenticated user id is missing from your session.')
      return
    }
    const deadline = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString()
    await runAction('plan', () =>
      planResources(processId, {
        task_id: crypto.randomUUID(),
        tenant_id: tenantId,
        correlation_id: crypto.randomUUID(),
        human_requirements: {
          resource_type: 'HUMAN',
          required_roles: ['developer'],
          mandatory_skills: ['python'],
          preferred_skills: ['fastapi'],
          requester_id: user.id,
          task_deadline: deadline,
          estimated_effort_hours: '8.00',
          process_stage: 'RESOURCE_PLANNING',
        },
        budget_requirements: {
          resource_type: 'BUDGET',
          required_amount: '5000.00',
          currency: 'USD',
          cost_centre: 'SYN-DEP-FIN',
          requester_id: user.id,
          task_deadline: deadline,
          process_stage: 'RESOURCE_PLANNING',
        },
      }),
    )
  }

  async function onRiskReview() {
    await runAction('risk', () => riskReview(processId))
  }

  async function onExecute() {
    const meta = (process?.metadata_json || {}) as Record<string, unknown>
    const purchase =
      meta.purchase_order && typeof meta.purchase_order === 'object'
        ? (meta.purchase_order as Record<string, unknown>)
        : {}
    const amountRaw = purchase.amount ?? meta.amount ?? meta.required_amount ?? 2500
    const amount = Number(amountRaw)
    const vendor = String(
      purchase.vendor_id ||
        purchase.vendor ||
        meta.vendor_id ||
        meta.vendor ||
        'VENDOR-ACME',
    )
    await runAction('execute', () =>
      executeProcess(processId, {
        task_id: crypto.randomUUID(),
        task_type: 'EXECUTE_TASK',
        correlation_id: crypto.randomUUID(),
        parameters: {
          tool_name: 'create_po_draft',
          vendor_id: vendor,
          amount: Number.isFinite(amount) && amount > 0 ? amount : 2500,
          items_summary: `${process?.name || 'Process'} procurement items`,
          process_id: processId,
        },
      }),
    )
  }

  async function onCompleteInvoice() {
    const amount = invoiceForm.amount.trim() ? Number(invoiceForm.amount) : undefined
    const expectedAmount = invoiceForm.expected_amount.trim()
      ? Number(invoiceForm.expected_amount)
      : undefined
    await runAction('invoice', () =>
      completeInvoiceMatching(processId, {
        invoice_number: invoiceForm.invoice_number.trim() || undefined,
        amount: Number.isFinite(amount) ? amount : undefined,
        currency: invoiceForm.currency.trim() || undefined,
        vendor: invoiceForm.vendor.trim() || undefined,
        po_reference: invoiceForm.po_reference.trim() || undefined,
        expected_amount: Number.isFinite(expectedAmount) ? expectedAmount : undefined,
        expected_po_reference: invoiceForm.expected_po_reference.trim() || undefined,
        expected_currency: invoiceForm.expected_currency.trim() || undefined,
        expected_vendor: invoiceForm.expected_vendor.trim() || undefined,
        notes: invoiceForm.notes.trim() || undefined,
      }),
    )
  }

  if (loading && !process) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-96 max-w-full" />
        <Skeleton className="h-28 w-full" />
        <div className="grid gap-6 lg:grid-cols-3">
          <Skeleton className="h-64 lg:col-span-2" />
          <Skeleton className="h-64" />
        </div>
      </div>
    )
  }

  if (!process && error) {
    return (
      <div className="space-y-4">
        <Link to="/processes" className="text-sm font-medium text-slate-600 hover:text-slate-900">
          ← Back to Processes
        </Link>
        <Alert tone="error">
          <div className="space-y-2">
            <p className="font-medium">Unable to load process</p>
            <p>{error}</p>
            <button type="button" className="btn btn-ghost btn-xs" onClick={() => void refresh()}>
              Retry
            </button>
          </div>
        </Alert>
      </div>
    )
  }

  if (!process) return null

  return (
    <div className="space-y-6">
      <div>
        <Link to="/processes" className="text-sm font-medium text-slate-500 hover:text-slate-800">
          ← Back to Processes
        </Link>
        <div className="mt-3">
          <PageHeader
            title={process.name}
            description={process.description || undefined}
            actions={
              <div className="flex flex-wrap items-center gap-2">
                <ProcessStageBadge stage={process.current_stage} />
              </div>
            }
          />
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-slate-600">
          <span className="font-medium text-slate-800">{formatProcessType(process.process_type)}</span>
          <span>
            Status: <span className="font-medium text-slate-800">{formatProcessStatus(process.status)}</span>
          </span>
          <span>
            Stage:{' '}
            <span className="font-medium text-slate-800">
              {formatProcessStage(process.current_stage)}
            </span>
          </span>
          <span className="text-slate-500">Created {formatDateTime(process.created_at)}</span>
          <span className="text-slate-500">Updated {formatDateTime(process.updated_at)}</span>
        </div>
      </div>

      {error ? (
        <Alert tone="error">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span>{error}</span>
            <button type="button" className="btn btn-ghost btn-xs" onClick={() => void refresh()}>
              Retry
            </button>
          </div>
        </Alert>
      ) : null}
      {notice ? <Alert tone="info">{notice}</Alert> : null}

      <StageStepper stage={process.current_stage} />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {/* Current step */}
          <Panel title="Current Step">
            <h3 className="text-base font-semibold text-slate-900">{stageMeta.title}</h3>
            <p className="mt-1 text-sm leading-relaxed text-slate-600">{stageMeta.body}</p>

            <div className="mt-5 space-y-3">
              {stage === 'DRAFT' ? (
                <div className="space-y-3">
                  <p className="text-sm text-slate-600">
                    Use Process Discovery below to upload process evidence. After discovery
                    completes, start the process journey to advance the stage.
                  </p>
                  {hasDiscoveryResults ? (
                    <button
                      type="button"
                      className="btn btn-primary btn-sm w-full sm:w-auto"
                      disabled={busy !== null}
                      onClick={() => void onStart()}
                    >
                      {busy === 'start' ? 'Starting Process...' : 'Start Process Discovery'}
                    </button>
                  ) : (
                    <p className="text-xs text-slate-500">
                      Upload process evidence first. Starting without discovery evidence may fail
                      until documents have been analyzed.
                    </p>
                  )}
                </div>
              ) : null}

              {stage === 'DISCOVERING' || stage === 'RESOURCE_PLANNING' ? (
                <button
                  type="button"
                  className="btn btn-primary btn-sm w-full sm:w-auto"
                  disabled={busy !== null || !user?.tenant_id}
                  onClick={() => void onPlanResources()}
                >
                  {busy === 'plan' ? 'Planning Resources...' : 'Run Resource Planning'}
                </button>
              ) : null}

              {stage === 'RISK_REVIEW' ? (
                <button
                  type="button"
                  className="btn btn-primary btn-sm w-full sm:w-auto"
                  disabled={busy !== null}
                  onClick={() => void onRiskReview()}
                >
                  {busy === 'risk' ? 'Running Risk Review...' : 'Run Risk Assessment'}
                </button>
              ) : null}

              {stage === 'AWAITING_HUMAN_APPROVAL' ? (
                <Link to="/approvals" className="btn btn-primary btn-sm w-full sm:w-auto">
                  Review Approval
                </Link>
              ) : null}

              {stage === 'WORKFLOW_EXECUTION' ? (
                <button
                  type="button"
                  className="btn btn-primary btn-sm w-full sm:w-auto"
                  disabled={busy !== null}
                  onClick={() => void onExecute()}
                >
                  {busy === 'execute' ? 'Executing Workflow...' : 'Run Workflow Execution'}
                </button>
              ) : null}

              {stage === 'INVOICE_MATCHING' ? (
                <div className="space-y-3">
                  <p className="text-sm text-slate-600">
                    Enter invoice evidence. Expected purchase values are filled from the PO created
                    during workflow execution when available. Completion requires a real match — a
                    note alone is not enough.
                  </p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {(
                      [
                        ['invoice_number', 'Invoice number'],
                        ['amount', 'Invoice amount'],
                        ['currency', 'Invoice currency'],
                        ['vendor', 'Invoice vendor'],
                        ['po_reference', 'Invoice PO reference'],
                        ['expected_amount', 'Expected amount'],
                        ['expected_currency', 'Expected currency'],
                        ['expected_po_reference', 'Expected PO reference'],
                        ['expected_vendor', 'Expected vendor'],
                        ['notes', 'Notes'],
                      ] as const
                    ).map(([key, label]) => (
                      <label key={key} className="block text-sm sm:col-span-1">
                        <span className="mb-1.5 block font-medium text-slate-700">{label}</span>
                        <input
                          value={invoiceForm[key]}
                          onChange={(e) =>
                            setInvoiceForm((prev) => ({ ...prev, [key]: e.target.value }))
                          }
                          className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-slate-400"
                          disabled={busy !== null}
                        />
                      </label>
                    ))}
                  </div>
                  <button
                    type="button"
                    className="btn btn-primary btn-sm w-full sm:w-auto"
                    disabled={busy !== null}
                    onClick={() => void onCompleteInvoice()}
                  >
                    {busy === 'invoice' ? 'Matching Invoice...' : 'Match Invoice'}
                  </button>
                </div>
              ) : null}

              {stage === 'EXCEPTION' ? (
                <Link to="/exceptions" className="btn btn-primary btn-sm w-full sm:w-auto">
                  View Exception
                </Link>
              ) : null}

              {stage === 'DISCOVERING' && !user?.tenant_id ? (
                <p className="text-xs text-amber-800">
                  Tenant context is required for resource planning. Ensure you are signed in.
                </p>
              ) : null}
            </div>
          </Panel>

          {/* Process Discovery — primary upload + review */}
          {stage === 'DRAFT' ||
          stage === 'DISCOVERING' ||
          stage === 'RESOURCE_PLANNING' ||
          stage === 'RISK_REVIEW' ||
          hasDiscoveryResults ? (
            <ProcessDiscoveryPanel
              processId={processId}
              discovery={discovery}
              latestMessage={latestDiscoveryMessage}
              stage={stage}
              onDiscoveryComplete={async (message) => {
                setLatestDiscoveryMessage(message)
                setNotice('Process discovery completed. Review the results below.')
                await refresh()
              }}
              showContinueToPlanning={stage === 'DISCOVERING'}
              onContinueToPlanning={() => void onPlanResources()}
              planningBusy={busy === 'plan'}
              planningDisabled={!user?.tenant_id}
            />
          ) : null}

          {/* Resource recommendation */}
          {(stage === 'RESOURCE_PLANNING' ||
            stage === 'RISK_REVIEW' ||
            stage === 'AWAITING_HUMAN_APPROVAL' ||
            resourcePayload) &&
          ['RESOURCE_PLANNING', 'RISK_REVIEW', 'AWAITING_HUMAN_APPROVAL', 'WORKFLOW_EXECUTION'].includes(
            stage,
          ) ? (
            <Panel title="Resource Recommendation">
              <p className="mb-3 text-sm text-slate-500">
                Advisory recommendation only — not a governance approval.
              </p>
              {resourcePayload ? (
                <div className="space-y-3 text-sm">
                  {typeof resourcePayload.recommendation_id === 'string' ||
                  typeof resourcePayload.recommendation_status === 'string' ||
                  typeof resourcePayload.message === 'string' ? (
                    <dl className="grid gap-3 sm:grid-cols-2">
                      {typeof resourcePayload.recommendation_status === 'string' ? (
                        <div>
                          <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">
                            Status
                          </dt>
                          <dd className="mt-1 font-medium text-slate-800">
                            {String(resourcePayload.recommendation_status)}
                          </dd>
                        </div>
                      ) : null}
                      {typeof resourcePayload.recommendation_id === 'string' ? (
                        <div>
                          <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">
                            Recommendation ID
                          </dt>
                          <dd className="mt-1 break-all text-slate-700">
                            {String(resourcePayload.recommendation_id)}
                          </dd>
                        </div>
                      ) : null}
                      {typeof resourcePayload.message === 'string' ? (
                        <div className="sm:col-span-2">
                          <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">
                            Summary
                          </dt>
                          <dd className="mt-1 text-slate-700">{String(resourcePayload.message)}</dd>
                        </div>
                      ) : null}
                    </dl>
                  ) : null}
                  <details className="rounded-lg border border-slate-100 bg-slate-50/80">
                    <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-slate-600">
                      Full recommendation payload
                    </summary>
                    <pre className="max-h-48 overflow-auto border-t border-slate-100 p-3 text-xs text-slate-700">
                      {JSON.stringify(resourcePayload, null, 2)}
                    </pre>
                  </details>
                </div>
              ) : (
                <p className="text-sm text-slate-500">
                  No resource recommendation is available yet. Run resource planning when ready.
                </p>
              )}
            </Panel>
          ) : null}

          {/* Risk assessment */}
          {(stage === 'RISK_REVIEW' ||
            stage === 'AWAITING_HUMAN_APPROVAL' ||
            riskFromWorkflow.overall ||
            pendingApproval) &&
          stage !== 'DRAFT' &&
          stage !== 'DISCOVERING' ? (
            <Panel title="Risk Assessment">
              <p className="mb-4 text-sm text-slate-500">
                AI risk assessment informs whether human authorization is required. It does not approve
                the process.
              </p>
              <dl className="grid gap-4 sm:grid-cols-2">
                <div>
                  <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">
                    Risk Level
                  </dt>
                  <dd className="mt-1">
                    {riskFromWorkflow.overall || pendingApproval?.risk_level ? (
                      <RiskBadge
                        level={riskFromWorkflow.overall || pendingApproval!.risk_level}
                      />
                    ) : (
                      <span className="text-sm text-slate-500">Not available yet</span>
                    )}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">
                    Recommendation
                  </dt>
                  <dd className="mt-1 text-sm font-medium text-slate-800">
                    {stage === 'AWAITING_HUMAN_APPROVAL' ||
                    riskFromWorkflow.humanRequired ||
                    pendingApproval
                      ? 'Human Approval Required'
                      : lastWorkflow?.eligible_for_execution
                        ? 'Eligible for Execution'
                        : 'Awaiting assessment'}
                  </dd>
                </div>
              </dl>
              {(riskFromWorkflow.reason || pendingApproval?.reason) && (
                <div className="mt-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Reason</p>
                  <p className="mt-1 text-sm text-slate-700">
                    {riskFromWorkflow.reason || pendingApproval?.reason}
                  </p>
                </div>
              )}
            </Panel>
          ) : null}

          {/* Human approval */}
          {stage === 'AWAITING_HUMAN_APPROVAL' || pendingApproval ? (
            <Panel title="Human Approval Required">
              <div className="rounded-lg border border-amber-200/80 bg-amber-50/50 p-4">
                <p className="text-sm font-medium text-amber-950">
                  AI risk assessment indicates that human authorization is required before execution.
                </p>
                {pendingApproval ? (
                  <dl className="mt-4 grid gap-3 sm:grid-cols-2">
                    <div>
                      <dt className="text-xs uppercase tracking-wide text-amber-800/80">Risk Level</dt>
                      <dd className="mt-1">
                        <RiskBadge level={pendingApproval.risk_level} />
                      </dd>
                    </div>
                    <div className="sm:col-span-2">
                      <dt className="text-xs uppercase tracking-wide text-amber-800/80">Reason</dt>
                      <dd className="mt-1 text-sm text-amber-950">{pendingApproval.reason}</dd>
                    </div>
                  </dl>
                ) : null}
                <Link to="/approvals" className="btn btn-primary btn-sm mt-4">
                  Review Approval
                </Link>
              </div>
            </Panel>
          ) : null}

          {/* Human decision result */}
          {decidedApproval && decidedApproval.status === 'APPROVED' ? (
            <Panel title="Approved by Human">
              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-xs uppercase tracking-wide text-slate-500">Decision</dt>
                  <dd className="mt-1 font-medium text-emerald-800">Approved</dd>
                </div>
                {decidedApproval.approver_id ? (
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-slate-500">Approver</dt>
                    <dd className="mt-1 font-mono text-xs text-slate-700">
                      {decidedApproval.approver_id}
                    </dd>
                  </div>
                ) : null}
                <div>
                  <dt className="text-xs uppercase tracking-wide text-slate-500">Decided</dt>
                  <dd className="mt-1 text-slate-700">{formatDateTime(decidedApproval.decided_at)}</dd>
                </div>
                {decidedApproval.comments ? (
                  <div className="sm:col-span-2">
                    <dt className="text-xs uppercase tracking-wide text-slate-500">Comments</dt>
                    <dd className="mt-1 text-slate-700">{decidedApproval.comments}</dd>
                  </div>
                ) : null}
              </dl>
              {stage === 'WORKFLOW_EXECUTION' || lastWorkflow?.eligible_for_execution ? (
                <p className="mt-4 text-sm font-medium text-slate-800">Ready for Execution</p>
              ) : null}
            </Panel>
          ) : null}

          {decidedApproval && decidedApproval.status === 'REJECTED' ? (
            <Panel title="Approval Rejected">
              <p className="text-sm text-slate-600">
                A human rejected this process. The backend determines the resulting stage — typically
                Exception.
              </p>
              <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-xs uppercase tracking-wide text-slate-500">Decision</dt>
                  <dd className="mt-1 font-medium text-rose-800">Rejected</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wide text-slate-500">Decided</dt>
                  <dd className="mt-1">{formatDateTime(decidedApproval.decided_at)}</dd>
                </div>
                {decidedApproval.comments ? (
                  <div className="sm:col-span-2">
                    <dt className="text-xs uppercase tracking-wide text-slate-500">Comments</dt>
                    <dd className="mt-1">{decidedApproval.comments}</dd>
                  </div>
                ) : null}
              </dl>
            </Panel>
          ) : null}

          {/* Execution */}
          {(stage === 'WORKFLOW_EXECUTION' ||
            stage === 'INVOICE_MATCHING' ||
            stage === 'COMPLETED' ||
            receipts.length > 0) &&
          stage !== 'DRAFT' &&
          stage !== 'DISCOVERING' ? (
            <Panel title="Workflow Execution">
              {receipts.length === 0 ? (
                <p className="text-sm text-slate-500">
                  No execution receipts are available for this process yet.
                </p>
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    <div className="rounded-lg border border-slate-100 bg-slate-50/70 px-3 py-2">
                      <p className="text-xs text-slate-500">Actions</p>
                      <p className="text-lg font-semibold tabular-nums text-slate-900">
                        {receiptSummary.total}
                      </p>
                    </div>
                    <div className="rounded-lg border border-slate-100 bg-slate-50/70 px-3 py-2">
                      <p className="text-xs text-slate-500">Successful</p>
                      <p className="text-lg font-semibold tabular-nums text-slate-900">
                        {receiptSummary.successful}
                      </p>
                    </div>
                    <div className="rounded-lg border border-slate-100 bg-slate-50/70 px-3 py-2">
                      <p className="text-xs text-slate-500">Failed</p>
                      <p className="text-lg font-semibold tabular-nums text-slate-900">
                        {receiptSummary.failed}
                      </p>
                    </div>
                    <div className="rounded-lg border border-slate-100 bg-slate-50/70 px-3 py-2">
                      <p className="text-xs text-slate-500">Blocked</p>
                      <p className="text-lg font-semibold tabular-nums text-slate-900">
                        {receiptSummary.blocked}
                      </p>
                    </div>
                  </div>
                  {receiptSummary.blocked > 0 || receiptSummary.failed > 0 ? (
                    <div className="mt-4 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-600">
                      <p className="font-medium text-slate-800">Execution Safety</p>
                      <p className="mt-1 text-xs">
                        Execution is controlled and authorized. Blocked or failed actions are recorded
                        in receipts without exposing internal security details.
                      </p>
                    </div>
                  ) : null}
                  <ul className="mt-4 divide-y divide-slate-100">
                    {receipts.slice(0, 6).map((r) => (
                      <li key={r.id} className="flex items-start justify-between gap-3 py-2.5 text-sm">
                        <div className="min-w-0">
                          <p className="truncate font-medium text-slate-800">
                            {r.tool_name} · {r.action}
                          </p>
                          <p className="text-xs text-slate-500">{formatDateTime(r.created_at)}</p>
                        </div>
                        <span className="shrink-0 text-xs font-medium uppercase tracking-wide text-slate-500">
                          {r.status}
                        </span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </Panel>
          ) : null}

          {/* Exception */}
          {stage === 'EXCEPTION' || openException ? (
            <Panel title="Exception">
              {openException ? (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <RiskBadge level={openException.severity} />
                    <span className="text-sm text-slate-600">
                      {formatExceptionStatus(openException.status)}
                    </span>
                    <span className="text-sm text-slate-500">{openException.type}</span>
                  </div>
                  <p className="text-sm text-slate-700">{openException.description}</p>
                  {openException.resolution_notes ? (
                    <p className="text-sm text-slate-500">
                      Notes: {openException.resolution_notes}
                    </p>
                  ) : null}
                  <Link to="/exceptions" className="btn btn-ghost btn-sm">
                    View Exception
                  </Link>
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-sm text-slate-600">
                    This process is in an exception state. Open Exceptions for details.
                  </p>
                  <Link to="/exceptions" className="btn btn-primary btn-sm">
                    View Exception
                  </Link>
                </div>
              )}
            </Panel>
          ) : null}

          {/* Completed */}
          {stage === 'COMPLETED' ? (
            <Panel>
              <div className="py-2 text-center sm:text-left">
                <p className="text-base font-semibold text-slate-900">✓ Process Completed</p>
                <p className="mt-1 text-sm text-slate-600">
                  {process.name} completed successfully.
                </p>
                <p className="mt-2 text-xs text-slate-500">
                  Updated {formatDateTime(process.updated_at)}
                </p>
              </div>
            </Panel>
          ) : null}

          {/* Timeline */}
          <Panel title="Process Timeline">
            {audit.length === 0 ? (
              <EmptyState
                title="No timeline events yet"
                body="Activity will appear here when audit data is available for this process."
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
        </div>

        {/* Sidebar */}
        <aside className="space-y-6 lg:col-span-1">
          <Panel title="Process Information">
            <dl className="space-y-3 text-sm">
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Process ID</dt>
                <dd className="mt-1 break-all font-mono text-xs text-slate-700">{process.id}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Type</dt>
                <dd className="mt-1 text-slate-800">{formatProcessType(process.process_type)}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Status</dt>
                <dd className="mt-1 text-slate-800">{formatProcessStatus(process.status)}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Current Stage</dt>
                <dd className="mt-1">
                  <ProcessStageBadge stage={process.current_stage} />
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Version</dt>
                <dd className="mt-1 text-slate-800">{process.version}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Created</dt>
                <dd className="mt-1 text-slate-800">{formatDateTime(process.created_at)}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Last Updated</dt>
                <dd className="mt-1 text-slate-800">{formatDateTime(process.updated_at)}</dd>
              </div>
              {process.created_by ? (
                <div>
                  <dt className="text-xs uppercase tracking-wide text-slate-500">Created By</dt>
                  <dd className="mt-1 break-all font-mono text-xs text-slate-700">
                    {process.created_by}
                  </dd>
                </div>
              ) : null}
            </dl>
          </Panel>

          <Panel title="Quick links">
            <ul className="space-y-2 text-sm">
              <li>
                <Link to="/approvals" className="font-medium text-slate-700 hover:text-slate-900">
                  Approvals
                </Link>
              </li>
              <li>
                <Link to="/exceptions" className="font-medium text-slate-700 hover:text-slate-900">
                  Exceptions
                </Link>
              </li>
              <li>
                <Link to="/audit" className="font-medium text-slate-700 hover:text-slate-900">
                  Audit Trail
                </Link>
              </li>
            </ul>
          </Panel>
        </aside>
      </div>
    </div>
  )
}
