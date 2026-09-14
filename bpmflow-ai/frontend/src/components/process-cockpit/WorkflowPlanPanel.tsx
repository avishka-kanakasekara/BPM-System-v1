import { Link } from 'react-router-dom'
import type {
  WorkflowPlanRecord,
  WorkflowPlanValidationResult,
  WorkflowStepExecutionResult,
  WorkflowStepRecord,
} from '../../types/api'
import { Alert, Badge, EmptyState, Panel } from '../ui/primitives'
import { formatDateTime, isStepExecutableInUi } from './helpers'

function stepStatusTone(status: string): 'neutral' | 'good' | 'warn' | 'bad' | 'info' {
  const key = status.toUpperCase()
  if (key === 'COMPLETED') return 'good'
  if (key === 'FAILED' || key === 'EXCEPTION') return 'bad'
  if (key === 'AUTHORIZED' || key === 'READY') return 'info'
  if (key === 'WAITING_HUMAN_APPROVAL' || key === 'WAITING_DEPENDENCY') return 'warn'
  return 'neutral'
}

export default function WorkflowPlanPanel({
  processStage,
  plan,
  steps,
  validation,
  loading,
  error,
  canActivate,
  canGenerate,
  busy,
  lastExecution,
  onGenerate,
  onValidate,
  onActivate,
  onExecuteStep,
}: {
  processStage: string
  plan: WorkflowPlanRecord | null
  steps: WorkflowStepRecord[]
  validation: WorkflowPlanValidationResult | null
  loading: boolean
  error: string | null
  canActivate: boolean
  canGenerate: boolean
  busy: string | null
  lastExecution: WorkflowStepExecutionResult | null
  onGenerate: () => void
  onValidate: () => void
  onActivate: () => void
  onExecuteStep: (step: WorkflowStepRecord) => void
}) {
  const ordered = [...steps].sort((a, b) => a.sequence - b.sequence)
  const planStatus = String(plan?.status || '')
  const showActivate =
    canActivate &&
    Boolean(plan) &&
    planStatus !== 'ACTIVE' &&
    planStatus !== 'COMPLETED' &&
    planStatus !== 'CANCELLED' &&
    planStatus !== 'SUPERSEDED'
  const showValidate = Boolean(plan) && planStatus !== 'COMPLETED'
  const blocking = validation?.issues?.filter((i) => i.message) ?? []

  return (
    <Panel
      title="Workflow Plan"
      actions={
        <div className="flex flex-wrap gap-2">
          {canGenerate ? (
            <button
              type="button"
              className="btn btn-ghost btn-xs"
              disabled={busy !== null}
              onClick={onGenerate}
            >
              {busy === 'plan-generate' ? 'Generating…' : plan ? 'Generate new plan' : 'Generate plan'}
            </button>
          ) : null}
          {showValidate ? (
            <button
              type="button"
              className="btn btn-ghost btn-xs"
              disabled={busy !== null || !plan}
              onClick={onValidate}
            >
              {busy === 'plan-validate' ? 'Validating…' : 'Validate plan'}
            </button>
          ) : null}
        </div>
      }
    >
      {loading ? <p className="text-sm text-slate-500">Loading workflow plan…</p> : null}
      {error ? <Alert tone="error">{error}</Alert> : null}

      {!loading && !plan ? (
        <EmptyState
          title="No workflow plan yet"
          body="Generate a plan from Process Context. Creating a plan does not activate it and does not start Agent 2."
          action={
            canGenerate ? (
              <button type="button" className="btn btn-primary btn-sm" disabled={busy !== null} onClick={onGenerate}>
                {busy === 'plan-generate' ? 'Generating…' : 'Generate plan'}
              </button>
            ) : null
          }
        />
      ) : null}

      {plan ? (
        <div className="space-y-4">
          <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Plan ID</dt>
              <dd className="mt-1 break-all font-mono text-xs">{plan.id}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Version</dt>
              <dd className="mt-1">{plan.version}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Status</dt>
              <dd className="mt-1">
                <Badge>{planStatus || 'Unknown'}</Badge>
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Created</dt>
              <dd className="mt-1">{formatDateTime(plan.created_at)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Updated</dt>
              <dd className="mt-1">{formatDateTime(plan.updated_at)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Validation</dt>
              <dd className="mt-1">
                {validation == null
                  ? 'Not validated in this session'
                  : validation.valid
                    ? 'Valid'
                    : 'Blocking issues'}
              </dd>
            </div>
          </dl>

          {validation && !validation.valid ? (
            <Alert tone="warning">
              <p className="font-medium">Plan is not ready to activate</p>
              <ul className="mt-2 list-disc space-y-1 pl-4">
                {blocking.map((issue) => (
                  <li key={`${issue.code}-${issue.step_key ?? ''}`}>
                    {issue.code}: {issue.message}
                    {issue.step_key ? ` (${issue.step_key})` : ''}
                  </li>
                ))}
              </ul>
            </Alert>
          ) : null}

          {showActivate ? (
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
              <p className="text-sm font-medium text-slate-900">Activate workflow</p>
              <p className="mt-1 text-sm text-slate-600">
                Activation authorizes the workflow plan for execution. It does not run steps automatically.
              </p>
              <button
                type="button"
                className="btn btn-primary btn-sm mt-3"
                disabled={busy !== null}
                onClick={onActivate}
              >
                {busy === 'plan-activate' ? 'Activating…' : 'Activate workflow'}
              </button>
            </div>
          ) : null}

          {ordered.length === 0 ? (
            <p className="text-sm text-slate-600">This plan has no steps yet.</p>
          ) : (
            <ol className="space-y-3">
              {ordered.map((step) => {
                const executable = isStepExecutableInUi({
                  processStage,
                  planStatus,
                  step,
                })
                return (
                  <li key={step.id} className="rounded-lg border border-slate-200 px-4 py-3">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-slate-900">
                          {step.sequence}. {step.name}
                        </p>
                        <p className="mt-0.5 text-xs text-slate-500">
                          {step.step_type}
                          {step.required_action ? ` · ${step.required_action}` : ''}
                          {step.required_tool_category ? ` · ${step.required_tool_category}` : ''}
                        </p>
                      </div>
                      <Badge tone={stepStatusTone(String(step.status))}>{String(step.status)}</Badge>
                    </div>
                    {step.description ? (
                      <p className="mt-2 text-sm text-slate-600">{step.description}</p>
                    ) : null}
                    <p className="mt-2 text-xs text-slate-600">
                      Agent 2 executes one authorized Workflow Step using an allow-listed registered tool. Not a free-form
                      tool picker.
                    </p>
                    <dl className="mt-3 grid gap-2 text-xs text-slate-600 sm:grid-cols-2">
                      <div>
                        <dt className="uppercase tracking-wide text-slate-400">Responsible</dt>
                        <dd className="mt-0.5 break-all">
                          {step.responsible_employee_id ? (
                            <Link className="link font-mono" to={`/directory/employees/${step.responsible_employee_id}`}>
                              {step.responsible_employee_id}
                            </Link>
                          ) : (
                            <span className="font-mono">
                              {step.responsible_resource_id ||
                                step.responsible_role_id ||
                                (step.assignment_unresolved ? 'Unresolved' : 'Unavailable')}
                            </span>
                          )}
                        </dd>
                      </div>
                      <div>
                        <dt className="uppercase tracking-wide text-slate-400">Department / role</dt>
                        <dd className="mt-0.5 break-all font-mono">
                          {step.responsible_department_id || step.responsible_role_id || 'Unavailable'}
                        </dd>
                      </div>
                      <div>
                        <dt className="uppercase tracking-wide text-slate-400">Registered tool</dt>
                        <dd className="mt-0.5">
                          {step.required_action || 'Unavailable'}
                          {step.required_tool_category ? ` · ${step.required_tool_category}` : ''}
                          {step.approval_required ? ' · authorization required' : ''}
                        </dd>
                      </div>
                      <div>
                        <dt className="uppercase tracking-wide text-slate-400">Execution status</dt>
                        <dd className="mt-0.5">{String(step.status)}</dd>
                      </div>
                      <div>
                        <dt className="uppercase tracking-wide text-slate-400">Dependencies</dt>
                        <dd className="mt-0.5">
                          {step.depends_on_step_keys?.length
                            ? step.depends_on_step_keys.join(', ')
                            : 'None'}
                        </dd>
                      </div>
                      <div>
                        <dt className="uppercase tracking-wide text-slate-400">Approval</dt>
                        <dd className="mt-0.5">
                          {step.approval_required ? step.approval_type || 'Required' : 'Not required'}
                        </dd>
                      </div>
                    </dl>
                    {step.evidence_refs?.length ? (
                      <p className="mt-2 text-xs text-slate-500">
                        Evidence: {step.evidence_refs.map((e) => e.evidence_id).join(', ')}
                      </p>
                    ) : null}
                    {step.policy_refs?.length ? (
                      <p className="mt-1 text-xs text-slate-500">
                        Policy: {step.policy_refs.map((p) => p.policy_id).join(', ')}
                      </p>
                    ) : null}
                    {step.risk_level ? (
                      <p className="mt-1 text-xs text-slate-500">Risk: {step.risk_level}</p>
                    ) : null}
                    {executable ? (
                      <button
                        type="button"
                        className="btn btn-primary btn-sm mt-3"
                        disabled={busy !== null}
                        onClick={() => onExecuteStep(step)}
                      >
                        {busy === `execute-${step.id}` ? 'Executing…' : 'Execute step'}
                      </button>
                    ) : null}
                  </li>
                )
              })}
            </ol>
          )}

          {lastExecution ? (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50/70 px-4 py-3 text-sm">
              <p className="font-medium text-emerald-950">Execution receipt</p>
              <dl className="mt-2 grid gap-2 sm:grid-cols-2">
                <div>
                  <dt className="text-xs uppercase text-emerald-800/80">Receipt ID</dt>
                  <dd className="break-all font-mono text-xs">{lastExecution.receipt_id ?? '—'}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase text-emerald-800/80">Status</dt>
                  <dd>{lastExecution.execution_status}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase text-emerald-800/80">Step</dt>
                  <dd className="break-all font-mono text-xs">{lastExecution.workflow_step_id}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase text-emerald-800/80">Tool / action</dt>
                  <dd>
                    {lastExecution.tool_name || lastExecution.action_code || 'Resolved by Tool Registry'}
                  </dd>
                </div>
              </dl>
              {lastExecution.error_message ? (
                <p className="mt-2 text-rose-800">{lastExecution.error_message}</p>
              ) : null}
              <p className="mt-2 text-xs text-emerald-900/80">
                The next step is not started automatically. Execute the next authorized step when it is ready.
              </p>
            </div>
          ) : null}
        </div>
      ) : null}
    </Panel>
  )
}
