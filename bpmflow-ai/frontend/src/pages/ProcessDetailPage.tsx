import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  activateWorkflowPlan,
  apiErrorMessage,
  completeInvoiceMatching,
  decideApproval,
  executeWorkflowStep,
  failException,
  getDiscoveredProcess,
  getProcess,
  getProcessMonitoring,
  getProcessPurchaseOrder,
  getProcessWorkflow,
  getVendor,
  listApprovals,
  listAuditLogs,
  listExecutionReceipts,
  listProcessExceptions,
  listProcessInvoices,
  listProcessQuotations,
  listTobeRecommendations,
  listWorkflowSteps,
  planProcessWorkflow,
  planResources,
  resolveException,
  retryException,
  riskReview,
  startProcess,
  validateWorkflowPlan,
  type AgentMessage,
  type ApprovalRecord,
  type AuditLogRecord,
  type ExecutionReceipt,
  type ProcessDetail,
  type ProcessRecord,
  type WorkflowResult,
} from '../services/apiClient'
import type {
  ExceptionRecord,
  InvoiceRecord,
  ProcessMonitoringReport,
  PurchaseOrderRecord,
  QuotationRecord,
  RiskFinding,
  TobeRecommendationRecord,
  VendorRecord,
  WorkflowPlanRecord,
  WorkflowPlanValidationResult,
  WorkflowStepExecutionResult,
  WorkflowStepRecord,
} from '../types/api'
import { PROCESS_STAGE_DESCRIPTIONS, type WorkflowStage } from '../lib/processStages'
import { useAuth } from '../auth/AuthContext'
import { buildCorrelationTimeline } from '../lib/correlationTimeline'
import { stageActions } from '../lib/stageActions'
import ProcessDiscoveryPanel from '../components/discovery/ProcessDiscoveryPanel'
import Agent3ProcessResultsPanel from '../components/resources/Agent3ProcessResultsPanel'
import {
  Alert,
  ApprovalStatusBadge,
  EmptyState,
  ExceptionStatusBadge,
  PageHeader,
  Panel,
  ProcessStageBadge,
  RiskBadge,
  Skeleton,
} from '../components/ui/primitives'
import { formatProcessStage } from '../lib/statusPresentation'
import ProcessStageTimeline from '../components/process-cockpit/ProcessStageTimeline'
import ProcessContextPanel from '../components/process-cockpit/ProcessContextPanel'
import SupervisionLegend from '../components/process-cockpit/SupervisionLegend'
import WorkflowPlanPanel from '../components/process-cockpit/WorkflowPlanPanel'
import ProcessProcurementSummary from '../components/procurement/ProcessProcurementSummary'
import InvoiceMatchResultView from '../components/procurement/InvoiceMatchResultView'
import { parseInvoiceMatch } from '../lib/procurement'
import {
  asRecord,
  canGovern,
  displayText,
  formatDateTime,
  formatProcessType,
} from '../components/process-cockpit/helpers'

function detailErrorMessage(err: unknown): string {
  const status = (err as { response?: { status?: number } })?.response?.status
  if (status === 401) return 'Your session has expired. Please sign in again.'
  if (status === 403) return "You don't have permission to perform this action."
  if (status === 409) return 'This action cannot be performed at the current process stage.'
  if (status === 503) return 'The BPMFlow AI service is temporarily unavailable.'
  return apiErrorMessage(err)
}

function isNotFound(err: unknown): boolean {
  return (err as { response?: { status?: number } })?.response?.status === 404
}

export default function ProcessDetailPage() {
  const { processId = '' } = useParams()
  const { user } = useAuth()
  const governor = canGovern(user?.role)

  const [process, setProcess] = useState<ProcessRecord | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [secondaryError, setSecondaryError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const [discovery, setDiscovery] = useState<ProcessDetail | null>(null)
  const [latestDiscoveryMessage, setLatestDiscoveryMessage] = useState<AgentMessage | null>(null)
  const [approvals, setApprovals] = useState<ApprovalRecord[]>([])
  const [audit, setAudit] = useState<AuditLogRecord[]>([])
  const [receipts, setReceipts] = useState<ExecutionReceipt[]>([])
  const [lastWorkflow, setLastWorkflow] = useState<WorkflowResult | null>(null)
  const [invoices, setInvoices] = useState<InvoiceRecord[]>([])
  const [quotations, setQuotations] = useState<QuotationRecord[]>([])
  const [purchaseOrder, setPurchaseOrder] = useState<PurchaseOrderRecord | null>(null)
  const [procurementVendor, setProcurementVendor] = useState<VendorRecord | null>(null)
  const [exceptions, setExceptions] = useState<ExceptionRecord[]>([])
  const [plan, setPlan] = useState<WorkflowPlanRecord | null>(null)
  const [steps, setSteps] = useState<WorkflowStepRecord[]>([])
  const [planLoading, setPlanLoading] = useState(false)
  const [planError, setPlanError] = useState<string | null>(null)
  const [validation, setValidation] = useState<WorkflowPlanValidationResult | null>(null)
  const [lastExecution, setLastExecution] = useState<WorkflowStepExecutionResult | null>(null)
  const [monitoring, setMonitoring] = useState<ProcessMonitoringReport | null>(null)
  const [tobeRecommendations, setTobeRecommendations] = useState<TobeRecommendationRecord[]>([])
  const [exceptionNotes, setExceptionNotes] = useState('')
  const [approvalComments, setApprovalComments] = useState('')

  const refresh = useCallback(async () => {
    if (!processId) return
    setLoading(true)
    setError(null)
    setSecondaryError(null)
    try {
      const row = await getProcess(processId)
      setProcess(row)

      const partialErrors: string[] = []

      const [
        approvalResult,
        auditResult,
        receiptResult,
        discoveryResult,
        invoiceResult,
        quoteResult,
        poResult,
        exceptionResult,
        planResult,
        monitorResult,
        tobeResult,
      ] = await Promise.all([
        governor
          ? listApprovals()
              .then((rows) => ({ ok: true as const, rows }))
              .catch((err) => ({ ok: false as const, err }))
          : Promise.resolve({ ok: true as const, rows: [] as ApprovalRecord[] }),
        listAuditLogs({ entity_type: 'process', entity_id: processId, limit: 40 })
          .then((rows) => ({ ok: true as const, rows }))
          .catch((err) => ({ ok: false as const, err })),
        listExecutionReceipts({ process_id: processId, limit: 50 })
          .then((rows) => ({ ok: true as const, rows }))
          .catch((err) => ({ ok: false as const, err })),
        getDiscoveredProcess(processId)
          .then((rows) => ({ ok: true as const, rows }))
          .catch((err) => ({ ok: false as const, err })),
        listProcessInvoices(processId)
          .then((rows) => ({ ok: true as const, rows }))
          .catch((err) => ({ ok: false as const, err })),
        listProcessQuotations(processId)
          .then((rows) => ({ ok: true as const, rows }))
          .catch((err) => ({ ok: false as const, err })),
        getProcessPurchaseOrder(processId)
          .then((row) => ({ ok: true as const, row }))
          .catch((err) => ({ ok: false as const, err })),
        listProcessExceptions(processId)
          .then((rows) => ({ ok: true as const, rows }))
          .catch((err) => ({ ok: false as const, err })),
        getProcessWorkflow(processId)
          .then((row) => ({ ok: true as const, row }))
          .catch((err) => ({ ok: false as const, err })),
        getProcessMonitoring(processId)
              .then((report) => ({ ok: true as const, report }))
              .catch((err) => ({ ok: false as const, err })),
        listTobeRecommendations(processId)
          .then((rows) => ({ ok: true as const, rows }))
          .catch((err) => ({ ok: false as const, err })),
      ])

      if (approvalResult.ok) {
        setApprovals(approvalResult.rows.filter((a) => a.process_id === processId))
      } else {
        setApprovals([])
        partialErrors.push(`Approvals: ${detailErrorMessage(approvalResult.err)}`)
      }
      if (auditResult.ok) setAudit(auditResult.rows)
      else {
        setAudit([])
        partialErrors.push(`Audit trail: ${detailErrorMessage(auditResult.err)}`)
      }
      if (receiptResult.ok) setReceipts(receiptResult.rows)
      else {
        setReceipts([])
        partialErrors.push(`Receipts: ${detailErrorMessage(receiptResult.err)}`)
      }
      if (discoveryResult.ok) setDiscovery(discoveryResult.rows)
      else {
        setDiscovery(null)
        if (!isNotFound(discoveryResult.err)) {
          partialErrors.push(`Discovery: ${detailErrorMessage(discoveryResult.err)}`)
        }
      }
      if (invoiceResult.ok) setInvoices(invoiceResult.rows)
      else setInvoices([])
      if (quoteResult.ok) setQuotations(quoteResult.rows)
      else setQuotations([])
      if (poResult.ok) setPurchaseOrder(poResult.row)
      else setPurchaseOrder(null)

      const vendorId =
        (poResult.ok ? poResult.row.vendor_id : null) ||
        (invoiceResult.ok ? invoiceResult.rows[0]?.vendor_id : null) ||
        (quoteResult.ok ? quoteResult.rows[0]?.vendor_id : null)
      if (vendorId) {
        try {
          setProcurementVendor(await getVendor(vendorId))
        } catch {
          setProcurementVendor(null)
        }
      } else {
        setProcurementVendor(null)
      }
      if (exceptionResult.ok) setExceptions(exceptionResult.rows)
      else {
        setExceptions([])
        if (!isNotFound(exceptionResult.err)) {
          partialErrors.push(`Exceptions: ${detailErrorMessage(exceptionResult.err)}`)
        }
      }

      if (planResult.ok) {
        setPlan(planResult.row)
        setPlanError(null)
        const fromPlan = planResult.row.steps ?? []
        if (fromPlan.length > 0) {
          setSteps(fromPlan)
        } else {
          try {
            setSteps(await listWorkflowSteps(planResult.row.id))
          } catch (err) {
            setSteps([])
            partialErrors.push(`Workflow steps: ${detailErrorMessage(err)}`)
          }
        }
      } else {
        setPlan(null)
        setSteps([])
        if (!isNotFound(planResult.err)) {
          setPlanError(detailErrorMessage(planResult.err))
        } else {
          setPlanError(null)
        }
      }

      if ('report' in monitorResult && monitorResult.ok) {
        setMonitoring(monitorResult.report)
      } else {
        setMonitoring(null)
      }
      if (tobeResult.ok) setTobeRecommendations(tobeResult.rows)
      else setTobeRecommendations([])

      if (partialErrors.length > 0) setSecondaryError(partialErrors.join(' · '))
    } catch (err) {
      setError(detailErrorMessage(err))
    } finally {
      setLoading(false)
      setPlanLoading(false)
    }
  }, [processId, governor])

  useEffect(() => {
    setLatestDiscoveryMessage(null)
    setLastExecution(null)
    setValidation(null)
    void refresh()
  }, [refresh])

  const stage = process?.current_stage ?? ''
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

  const riskFindings = useMemo((): RiskFinding[] => {
    const fromWorkflow = lastWorkflow?.risk_assessment?.findings
    if (fromWorkflow?.length) return fromWorkflow
    const meta = asRecord(process?.metadata_json)
    const stored = asRecord(meta?.last_risk_assessment)
    const findings = stored?.findings
    if (Array.isArray(findings)) {
      return findings.filter(
        (f): f is RiskFinding =>
          f != null && typeof f === 'object' && 'risk_type' in f && 'description' in f,
      )
    }
    return []
  }, [lastWorkflow, process?.metadata_json])

  const overallRisk =
    lastWorkflow?.risk_assessment?.overall_risk_level ||
    pendingApproval?.risk_level ||
    displayText(asRecord(process?.process_context)?.risk) ||
    null

  const correlationTimeline = useMemo(
    () =>
      buildCorrelationTimeline({
        audit,
        autonomousActions: [],
        receipts,
        correlationId: undefined,
      }),
    [audit, receipts],
  )

  const availableActions = useMemo(
    () =>
      stageActions({
        stage: (stage || 'DRAFT') as WorkflowStage,
        hasDiscovery: hasDiscoveryResults,
        hasTenant: Boolean(user?.tenant_id),
        busy: busy !== null,
        humanApprovalPending: Boolean(pendingApproval),
      }),
    [stage, hasDiscoveryResults, user?.tenant_id, busy, pendingApproval],
  )

  async function withBusy<T>(busyKey: string, work: () => Promise<T>): Promise<T | undefined> {
    setBusy(busyKey)
    setError(null)
    setNotice(null)
    try {
      return await work()
    } catch (err) {
      setError(detailErrorMessage(err))
      return undefined
    } finally {
      setBusy(null)
    }
  }

  async function onStartDiscoveryStage() {
    const result = await withBusy('start', () => startProcess(processId))
    if (!result) return
    setProcess(result.process)
    setNotice(result.message || 'Discovery stage started.')
    await refresh()
  }

  async function onPlanResources() {
    const tenantId = user?.tenant_id
    if (!tenantId) {
      setError('Tenant context is missing from your session. Sign in again and retry.')
      return
    }
    const result = await withBusy('plan', () =>
      planResources(processId, {
        task_id: processId,
        tenant_id: tenantId,
        correlation_id: crypto.randomUUID(),
      }),
    )
    if (!result) return
    setLastWorkflow(result)
    setNotice(result.message)
    await refresh()
  }

  async function onRunRiskReview() {
    const result = await withBusy('risk', () => riskReview(processId, {}))
    if (!result) return
    setLastWorkflow(result)
    setNotice(result.message)
    await refresh()
  }

  async function onMatchPersistedInvoice() {
    const result = await withBusy('invoice', () => completeInvoiceMatching(processId, {}))
    if (!result) return
    setLastWorkflow(result)
    setNotice(result.message)
    await refresh()
  }

  async function onGeneratePlan() {
    setPlanLoading(true)
    const result = await withBusy('plan-generate', () => planProcessWorkflow(processId))
    setPlanLoading(false)
    if (!result) return
    if (result.plan) {
      setPlan(result.plan)
      setSteps(result.plan.steps ?? result.steps ?? [])
    } else if (result.steps) {
      setSteps(result.steps)
    }
    if (result.issues?.length) {
      setValidation({
        valid: Boolean(result.structurally_valid),
        issues: result.issues.map((issue) => ({
          code: issue.code,
          message: issue.message,
          step_key: issue.step_key,
        })),
      })
    }
    setNotice('Workflow plan generated. Validate and activate are separate actions.')
    await refresh()
  }

  async function onValidatePlan() {
    if (!plan) return
    const result = await withBusy('plan-validate', () => validateWorkflowPlan(plan.id))
    if (!result) return
    setValidation(result)
    setNotice(result.valid ? 'Plan validated. Activation is a separate action.' : 'Plan has blocking issues.')
  }

  async function onActivatePlan() {
    if (!plan) return
    const result = await withBusy('plan-activate', () => activateWorkflowPlan(plan.id))
    if (!result) return
    setPlan(result)
    setNotice('Activation authorizes the workflow plan for execution.')
    await refresh()
  }

  async function onExecuteStep(step: WorkflowStepRecord) {
    if (!plan) return
    const result = await withBusy(`execute-${step.id}`, () =>
      executeWorkflowStep(plan.id, step.id, { process_id: processId }),
    )
    if (!result) return
    setLastExecution(result)
    setNotice(`Step ${result.execution_status}. The next step was not started automatically.`)
    await refresh()
  }

  async function onDecide(decision: 'approve' | 'reject') {
    if (!pendingApproval) return
    const result = await withBusy(decision, () =>
      decideApproval(pendingApproval.id, decision, approvalComments.trim() || undefined),
    )
    if (!result) return
    setNotice(decision === 'approve' ? 'Approval recorded.' : 'Rejection recorded.')
    await refresh()
  }

  async function onExceptionAction(kind: 'resolve' | 'retry' | 'fail', exceptionId: string) {
    const notes = exceptionNotes.trim()
    if ((kind === 'resolve' || kind === 'fail') && !notes) {
      setError('Resolution notes are required.')
      return
    }
    const result = await withBusy(`ex-${kind}`, () => {
      if (kind === 'resolve') return resolveException(exceptionId, notes)
      if (kind === 'retry') return retryException(exceptionId, notes || undefined)
      return failException(exceptionId, notes)
    })
    if (!result) return
    setNotice(`Exception ${kind} submitted. Recovery is not automatic.`)
    await refresh()
  }

  if (loading && !process) {
    return (
      <div className="space-y-6" aria-busy="true">
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

  const openExceptions = exceptions.filter((e) => e.status === 'open' || e.status === 'in_progress')
  const canGeneratePlan = Boolean(user?.tenant_id) && stage !== 'DRAFT' && stage !== 'COMPLETED'

  return (
    <div className="space-y-6">
      <div>
        <Link to="/processes" className="text-sm font-medium text-slate-500 hover:text-slate-800">
          ← Back to Processes
        </Link>
        <div className="mt-3">
          <PageHeader
            title={process.name}
            description={process.description || PROCESS_STAGE_DESCRIPTIONS[stage as WorkflowStage]}
            actions={
              <div className="flex flex-wrap items-center gap-2">
                <ProcessStageBadge stage={process.current_stage} />
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => void refresh()}>
                  Refresh
                </button>
              </div>
            }
          />
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-slate-600">
          <span>
            Process ID:{' '}
            <span className="break-all font-mono text-xs text-slate-800">{process.id}</span>
          </span>
          <span className="font-medium text-slate-800">{formatProcessType(process.process_type)}</span>
          <span>
            Status: <span className="font-medium text-slate-800">{process.status}</span>
          </span>
          <span>
            Stage:{' '}
            <span className="font-medium text-slate-800">{formatProcessStage(process.current_stage)}</span>
          </span>
          {process.created_by ? <span>Requester: {process.created_by}</span> : null}
          <span className="text-slate-500">Created {formatDateTime(process.created_at)}</span>
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
      {secondaryError ? (
        <Alert tone="warning">
          Some sections could not be loaded: {secondaryError}{' '}
          <button type="button" className="btn btn-ghost btn-xs" onClick={() => void refresh()}>
            Retry
          </button>
        </Alert>
      ) : null}
      {notice ? <Alert tone="info">{notice}</Alert> : null}

      <ProcessStageTimeline stage={process.current_stage} />
      <SupervisionLegend />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Panel title="Current action">
            <h3 className="text-base font-semibold text-slate-900">{formatProcessStage(stage)}</h3>
            <p className="mt-1 text-sm leading-relaxed text-slate-600">
              {PROCESS_STAGE_DESCRIPTIONS[(stage as WorkflowStage)] ||
                'Review the current process state and available actions.'}
            </p>

            <div className="mt-5 space-y-3">
              {stage === 'DRAFT'
                ? availableActions
                    .filter((a) => a.id === 'start_discovery_stage')
                    .map((action) => (
                      <div key={action.id} className="space-y-2">
                        <p className="text-sm text-slate-600">
                          Upload evidence below, then start discovery. This moves DRAFT to DISCOVERING. It does not run the process.
                        </p>
                        <button
                          type="button"
                          className="btn btn-primary btn-sm"
                          disabled={!action.enabled}
                          title={action.reason}
                          onClick={() => void onStartDiscoveryStage()}
                        >
                          {busy === 'start' ? 'Starting…' : 'Start discovery'}
                        </button>
                        {!action.enabled && action.reason ? (
                          <p className="text-xs text-slate-500">{action.reason}</p>
                        ) : null}
                      </div>
                    ))
                : null}

              {stage === 'DISCOVERING' || stage === 'RESOURCE_PLANNING'
                ? availableActions
                    .filter((a) => a.id === 'plan_resources')
                    .map((action) => (
                      <button
                        key={action.id}
                        type="button"
                        className="btn btn-primary btn-sm"
                        disabled={!action.enabled}
                        title={action.reason}
                        onClick={() => void onPlanResources()}
                      >
                        {busy === 'plan' ? 'Planning resources…' : 'Plan resources from directory'}
                      </button>
                    ))
                : null}

              {stage === 'RISK_REVIEW'
                ? availableActions
                    .filter((a) => a.id === 'run_risk_review')
                    .map((action) => (
                      <button
                        key={action.id}
                        type="button"
                        className="btn btn-primary btn-sm"
                        disabled={!action.enabled}
                        onClick={() => void onRunRiskReview()}
                      >
                        {busy === 'risk' ? 'Running risk review…' : 'Run risk review'}
                      </button>
                    ))
                : null}

              {stage === 'WORKFLOW_EXECUTION' ? (
                <p className="text-sm text-slate-600">
                  Execute one authorized workflow step at a time. Agent 2 does not run the full workflow automatically.
                </p>
              ) : null}

              {stage === 'INVOICE_MATCHING'
                ? availableActions
                    .filter((a) => a.id === 'match_persisted_invoice')
                    .map((action) => (
                      <button
                        key={action.id}
                        type="button"
                        className="btn btn-primary btn-sm"
                        disabled={!action.enabled}
                        onClick={() => void onMatchPersistedInvoice()}
                      >
                        {busy === 'invoice' ? 'Matching…' : 'Match persisted invoice'}
                      </button>
                    ))
                : null}

              {stage === 'COMPLETED' ? (
                <p className="text-sm text-slate-600">This process is complete. Execution actions are closed.</p>
              ) : null}
            </div>
          </Panel>

          {stage === 'DRAFT' ||
          stage === 'DISCOVERING' ||
          stage === 'RESOURCE_PLANNING' ||
          hasDiscoveryResults ? (
            <ProcessDiscoveryPanel
              processId={processId}
              discovery={discovery}
              latestMessage={latestDiscoveryMessage}
              stage={stage}
              onDiscoveryComplete={async (message) => {
                setLatestDiscoveryMessage(message)
                setNotice('Discovery finished. Review extracted facts; Agent 1 does not approve.')
                await refresh()
              }}
              showContinueToPlanning={stage === 'DISCOVERING'}
              onContinueToPlanning={() => void onPlanResources()}
              planningBusy={busy === 'plan'}
              planningDisabled={!user?.tenant_id}
            />
          ) : null}

          <Agent3ProcessResultsPanel
            processId={processId}
            stage={stage}
            metadataJson={(process.metadata_json || null) as Record<string, unknown> | null}
            workflowAgentResponse={
              lastWorkflow?.agent_response &&
              typeof lastWorkflow.agent_response === 'object' &&
              !Array.isArray(lastWorkflow.agent_response)
                ? (lastWorkflow.agent_response as Record<string, unknown>)
                : null
            }
            planningBusy={busy === 'plan'}
            planningDisabled={!user?.tenant_id}
            onPlanResources={
              stage === 'DISCOVERING' || stage === 'RESOURCE_PLANNING' ? () => void onPlanResources() : undefined
            }
          />

          {(stage === 'RISK_REVIEW' ||
            stage === 'AWAITING_HUMAN_APPROVAL' ||
            overallRisk ||
            riskFindings.length > 0) &&
          stage !== 'DRAFT' &&
          stage !== 'DISCOVERING' ? (
            <Panel title="Risk review">
              <p className="mb-4 text-sm text-slate-500">
                Risk values come from Agent 4. The frontend does not override them.
              </p>
              <dl className="grid gap-4 sm:grid-cols-2">
                <div>
                  <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Risk level</dt>
                  <dd className="mt-1">
                    {overallRisk ? <RiskBadge level={overallRisk} /> : <span className="text-sm text-slate-500">Not available yet</span>}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Human gate</dt>
                  <dd className="mt-1 text-sm">
                    {stage === 'AWAITING_HUMAN_APPROVAL' || lastWorkflow?.human_approval_required
                      ? 'Human approval required'
                      : 'Not currently waiting'}
                  </dd>
                </div>
              </dl>
              {riskFindings.length > 0 ? (
                <ul className="mt-4 divide-y divide-slate-100 rounded-lg border border-slate-200">
                  {riskFindings.map((finding, idx) => (
                    <li key={`${finding.risk_type}-${idx}`} className="px-3 py-3 text-sm">
                      <div className="flex flex-wrap items-center gap-2">
                        <RiskBadge level={finding.risk_level} />
                        <span className="font-medium text-slate-900">{finding.risk_type}</span>
                      </div>
                      <p className="mt-1 text-slate-700">{finding.description}</p>
                      {finding.recommendation ? (
                        <p className="mt-1 text-xs text-slate-500">{finding.recommendation}</p>
                      ) : null}
                      {finding.policy_version || finding.evidence_refs?.length ? (
                        <p className="mt-1 text-xs text-slate-500">
                          {finding.policy_version ? `Policy ${finding.policy_version}` : ''}
                          {finding.evidence_refs?.length ? ` · Evidence ${finding.evidence_refs.join(', ')}` : ''}
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-4 text-sm text-slate-500">No risk findings were returned.</p>
              )}
            </Panel>
          ) : null}

          {stage === 'AWAITING_HUMAN_APPROVAL' || pendingApproval ? (
            <Panel title="Human approval">
              {governor ? (
                <div className="space-y-4">
                  <p className="text-sm text-slate-600">
                    Approve or reject using the backend approval APIs. There is no request-changes action.
                  </p>
                  {pendingApproval ? (
                    <>
                      <dl className="grid gap-3 text-sm sm:grid-cols-2">
                        <div>
                          <dt className="text-xs uppercase text-slate-500">Status</dt>
                          <dd className="mt-1">
                            <ApprovalStatusBadge status={pendingApproval.status} />
                          </dd>
                        </div>
                        <div>
                          <dt className="text-xs uppercase text-slate-500">Assigned approver</dt>
                          <dd className="mt-1 break-all font-mono text-xs">{pendingApproval.approver_id || '—'}</dd>
                        </div>
                        <div className="sm:col-span-2">
                          <dt className="text-xs uppercase text-slate-500">What requires approval</dt>
                          <dd className="mt-1">{pendingApproval.reason}</dd>
                        </div>
                        <div>
                          <dt className="text-xs uppercase text-slate-500">Requester</dt>
                          <dd className="mt-1 break-all font-mono text-xs">{pendingApproval.requested_by || process.created_by || '—'}</dd>
                        </div>
                        <div>
                          <dt className="text-xs uppercase text-slate-500">Amount</dt>
                          <dd className="mt-1">
                            {displayText(asRecord(asRecord(process.process_context)?.purchase)?.amount) || '—'}{' '}
                            {displayText(asRecord(asRecord(process.process_context)?.purchase)?.currency)}
                          </dd>
                        </div>
                      </dl>
                      <label className="block text-sm">
                        <span className="text-xs uppercase tracking-wide text-slate-500">Comments (optional)</span>
                        <textarea
                          className="textarea textarea-bordered mt-1 w-full text-sm"
                          rows={2}
                          value={approvalComments}
                          onChange={(e) => setApprovalComments(e.target.value)}
                        />
                      </label>
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          className="btn btn-primary btn-sm"
                          disabled={busy !== null}
                          onClick={() => void onDecide('approve')}
                        >
                          {busy === 'approve' ? 'Approving…' : 'Approve'}
                        </button>
                        <button
                          type="button"
                          className="btn btn-outline btn-sm"
                          disabled={busy !== null}
                          onClick={() => void onDecide('reject')}
                        >
                          {busy === 'reject' ? 'Rejecting…' : 'Reject'}
                        </button>
                      </div>
                    </>
                  ) : (
                    <p className="text-sm text-slate-600">No pending approval record was returned for this process.</p>
                  )}
                </div>
              ) : (
                <p className="text-sm font-medium text-slate-800">Waiting for an authorized approver.</p>
              )}
            </Panel>
          ) : null}

          <ProcessProcurementSummary
            processId={processId}
            quotations={quotations}
            purchaseOrder={purchaseOrder}
            invoices={invoices}
            vendor={procurementVendor}
          />

          {stage !== 'DRAFT' ? (
            <WorkflowPlanPanel
              processStage={stage}
              plan={plan}
              steps={steps}
              validation={validation}
              loading={planLoading && !plan}
              error={planError}
              canActivate={governor}
              canGenerate={canGeneratePlan}
              busy={busy}
              lastExecution={lastExecution}
              onGenerate={() => void onGeneratePlan()}
              onValidate={() => void onValidatePlan()}
              onActivate={() => void onActivatePlan()}
              onExecuteStep={(step) => void onExecuteStep(step)}
            />
          ) : null}

          {stage === 'INVOICE_MATCHING' || stage === 'COMPLETED' || invoices.length > 0 ? (
            <Panel title="Invoice matching">
              <p className="mb-3 text-sm text-slate-600">
                Matching uses persisted invoices against the purchase order. Caller-supplied expected totals are not used.
              </p>
              {purchaseOrder ? (
                <p className="mb-3 text-sm">
                  <Link className="link" to={`/purchase-orders/${processId}`}>
                    PO {purchaseOrder.po_number}
                  </Link>
                  {' · '}
                  {String(purchaseOrder.total)} {purchaseOrder.currency} · {purchaseOrder.status}
                </p>
              ) : (
                <p className="mb-3 text-sm text-slate-500">No purchase order record was returned.</p>
              )}
              {invoices.length === 0 ? (
                <EmptyState
                  title="No persisted invoices"
                  body="No invoice records were returned for this process. Matching uses persisted invoices, not values typed in the browser."
                />
              ) : (
                <ul className="space-y-3">
                  {invoices.map((inv) => (
                    <li key={inv.invoice_id} className="rounded-lg border border-slate-200 px-3 py-3 text-sm">
                      <p className="font-medium">
                        <Link className="link" to={`/invoices/${inv.invoice_id}`}>
                          {inv.invoice_number}
                        </Link>
                        {' · '}
                        {String(inv.total)} {inv.currency}
                      </p>
                      <p className="text-xs text-slate-500">
                        Status {inv.status}
                        {inv.invoice_date ? ` · ${inv.invoice_date}` : ''}
                      </p>
                      <div className="mt-2">
                        <InvoiceMatchResultView result={parseInvoiceMatch(inv.match_result)} />
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          ) : null}

          {stage === 'EXCEPTION' || openExceptions.length > 0 ? (
            <Panel title="Exception">
              {exceptions.length === 0 ? (
                <EmptyState
                  title="No exception records"
                  body="The process is in EXCEPTION but no exception rows were returned. Refresh or check audit."
                />
              ) : (
                <ul className="space-y-4">
                  {exceptions.map((ex) => (
                    <li key={ex.id} className="rounded-lg border border-rose-200 px-4 py-3">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <p className="font-medium text-slate-900">{ex.title || ex.exception_code || 'Exception'}</p>
                          <p className="text-xs text-slate-500">
                            {ex.exception_code || ex.type} · {formatDateTime(ex.created_at)}
                          </p>
                        </div>
                        <ExceptionStatusBadge status={ex.status} />
                        <Link className="link text-sm" to={`/exceptions/${ex.id}`}>
                          View exception
                        </Link>
                      </div>
                      <p className="mt-2 text-sm text-slate-700">{ex.description}</p>
                      {ex.workflow_step_id ? (
                        <p className="mt-1 break-all font-mono text-xs text-slate-500">
                          Step {ex.workflow_step_id}
                          {ex.workflow_plan_id ? ` · plan ${ex.workflow_plan_id}` : ''}
                        </p>
                      ) : null}
                      {ex.evidence_refs?.length ? (
                        <p className="mt-1 text-xs text-slate-500">Evidence: {ex.evidence_refs.join(', ')}</p>
                      ) : null}
                      {ex.resolution_notes ? (
                        <p className="mt-1 text-xs text-slate-600">Resolution: {ex.resolution_notes}</p>
                      ) : null}
                      {governor && (ex.status === 'open' || ex.status === 'in_progress') ? (
                        <div className="mt-3 space-y-2">
                          <textarea
                            className="textarea textarea-bordered w-full text-sm"
                            rows={2}
                            placeholder="Resolution notes (required for resolve/fail)"
                            value={exceptionNotes}
                            onChange={(e) => setExceptionNotes(e.target.value)}
                          />
                          <div className="flex flex-wrap gap-2">
                            <button
                              type="button"
                              className="btn btn-sm"
                              disabled={busy !== null}
                              onClick={() => void onExceptionAction('resolve', ex.id)}
                            >
                              Resolve
                            </button>
                            <button
                              type="button"
                              className="btn btn-sm btn-ghost"
                              disabled={busy !== null}
                              onClick={() => void onExceptionAction('retry', ex.id)}
                            >
                              Retry
                            </button>
                            <button
                              type="button"
                              className="btn btn-sm btn-outline"
                              disabled={busy !== null}
                              onClick={() => void onExceptionAction('fail', ex.id)}
                            >
                              Fail
                            </button>
                          </div>
                          <p className="text-xs text-slate-500">Actions are not automatic. The API remains authoritative.</p>
                        </div>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          ) : null}

          {stage === 'COMPLETED' ? (
            <Panel title="Completion summary">
              <p className="text-sm text-slate-700">{process.name} is completed. Execution actions are closed.</p>
              <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-xs uppercase text-slate-500">PO</dt>
                  <dd>{purchaseOrder?.po_number ?? '—'}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase text-slate-500">Invoice</dt>
                  <dd>{invoices[0]?.invoice_number ?? '—'}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase text-slate-500">Workflow steps completed</dt>
                  <dd>{steps.filter((s) => String(s.status).toUpperCase() === 'COMPLETED').length}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase text-slate-500">Receipts</dt>
                  <dd>{receipts.length}</dd>
                </div>
              </dl>
              {monitoring ? (
                <div className="mt-4 space-y-2 text-sm">
                  {monitoring.kpis.insufficient_evidence ? (
                    <p className="text-amber-800">Insufficient evidence in the monitoring KPI report.</p>
                  ) : null}
                  <p className="text-xs text-slate-500">
                    Completion rate {String(monitoring.kpis.completion_rate ?? '—')} · exceptions{' '}
                    {monitoring.kpis.total_exceptions ?? 0} · bottlenecks {monitoring.bottlenecks?.length ?? 0}
                  </p>
                </div>
              ) : (
                <p className="mt-3 text-sm text-slate-500">No monitoring data.</p>
              )}
              <div className="mt-3 flex flex-wrap gap-2">
                <Link className="btn btn-ghost btn-sm" to={`/processes/${processId}/monitoring`}>
                  Open monitoring
                </Link>
                <Link className="btn btn-ghost btn-sm" to={`/recommendations?process=${processId}`}>
                  TO-BE recommendations
                </Link>
              </div>
            </Panel>
          ) : null}

          {stage !== 'DRAFT' && (monitoring || tobeRecommendations.length > 0) ? (
            <Panel title="Monitoring">
              <p className="mb-3 text-sm text-slate-600">
                TO-BE provides recommendations for human review; it does not automatically change the workflow.
              </p>
              {monitoring?.kpis.insufficient_evidence ? (
                <Alert tone="warning">Insufficient evidence. Values below are backend-returned.</Alert>
              ) : null}
              {monitoring ? (
                <dl className="grid gap-3 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Exceptions</dt>
                    <dd>{monitoring.exception_analytics?.total_exceptions ?? monitoring.kpis.total_exceptions ?? 0}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Observed bottlenecks</dt>
                    <dd>{monitoring.bottlenecks?.length ?? 0}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Human wait</dt>
                    <dd>
                      {monitoring.kpis.average_human_wait_time_seconds == null
                        ? 'Duration unavailable'
                        : `${monitoring.kpis.average_human_wait_time_seconds} s`}
                    </dd>
                  </div>
                </dl>
              ) : (
                <p className="text-sm text-slate-500">No monitoring report.</p>
              )}
              {tobeRecommendations.length > 0 ? (
                <p className="mt-3 text-sm">
                  <Link className="link" to={`/recommendations/${tobeRecommendations[0].id}`}>
                    {tobeRecommendations[0].title}
                  </Link>
                </p>
              ) : null}
              <div className="mt-3 flex flex-wrap gap-2">
                <Link className="btn btn-ghost btn-sm" to={`/processes/${processId}/monitoring`}>
                  Open monitoring
                </Link>
                <Link className="btn btn-ghost btn-sm" to={`/recommendations?process=${processId}`}>
                  TO-BE recommendations
                </Link>
              </div>
            </Panel>
          ) : null}

          {receipts.length > 0 && stage !== 'DRAFT' ? (
            <Panel title="Execution receipts">
              <ul className="divide-y divide-slate-100">
                {receipts.slice(0, 8).map((r) => (
                  <li key={r.id} className="flex items-start justify-between gap-3 py-2.5 text-sm">
                    <div className="min-w-0">
                      <p className="truncate font-medium text-slate-800">
                        {r.tool_name} · {r.action}
                      </p>
                      <p className="break-all text-xs text-slate-500">
                        {r.id} · {formatDateTime(r.created_at)}
                      </p>
                    </div>
                    <span className="shrink-0 text-xs font-medium uppercase text-slate-500">{r.status}</span>
                  </li>
                ))}
              </ul>
            </Panel>
          ) : null}

          <Panel title="Activity">
            {correlationTimeline.length === 0 ? (
              <EmptyState
                title="No timeline events yet"
                body="Audit entries and execution receipts appear here. Events are not invented in the browser."
              />
            ) : (
              <ol className="space-y-0">
                {correlationTimeline.slice(0, 24).map((event, idx) => (
                  <li key={event.id} className="flex gap-3">
                    <div className="flex w-4 flex-col items-center">
                      <span className="mt-1.5 h-2 w-2 rounded-full bg-slate-400" />
                      {idx < Math.min(correlationTimeline.length, 24) - 1 ? (
                        <span className="my-1 w-px flex-1 bg-slate-200" aria-hidden />
                      ) : null}
                    </div>
                    <div className="min-w-0 pb-4">
                      <p className="text-sm font-medium text-slate-800">{event.title}</p>
                      <p className="text-xs text-slate-500">{formatDateTime(event.timestamp)}</p>
                      {event.detail ? <p className="mt-0.5 text-xs text-slate-600">{event.detail}</p> : null}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </Panel>
        </div>

        <aside className="space-y-6 lg:col-span-1">
          <ProcessContextPanel context={process.process_context} />
          <Panel title="Process information">
            <dl className="space-y-3 text-sm">
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Process ID</dt>
                <dd className="mt-1 break-all font-mono text-xs">{process.id}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Version</dt>
                <dd className="mt-1">{process.version}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Updated</dt>
                <dd className="mt-1">{formatDateTime(process.updated_at)}</dd>
              </div>
            </dl>
          </Panel>
        </aside>
      </div>
    </div>
  )
}
