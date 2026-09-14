import { Link } from 'react-router-dom'
import { FullRecommendation } from '../../features/agent3/components/RecommendationPresentation'
import type { PersistedAllocationResponse } from '../../features/agent3/types/agent3Api'
import { Panel } from '../ui/primitives'
import {
  parseProcessAgent3Allocation,
  readStoredAgent3Allocation,
  writeStoredAgent3Allocation,
} from './parseProcessAgent3Allocation'
import { useEffect, useMemo, useState } from 'react'

const VISIBLE_STAGES = new Set([
  'RESOURCE_PLANNING',
  'RISK_REVIEW',
  'AWAITING_HUMAN_APPROVAL',
  'WORKFLOW_EXECUTION',
  'INVOICE_MATCHING',
  'COMPLETED',
  'EXCEPTION',
])

type Props = {
  processId: string
  stage: string
  metadataJson?: Record<string, unknown> | null
  workflowAgentResponse?: Record<string, unknown> | null
  planningBusy?: boolean
  planningDisabled?: boolean
  onPlanResources?: () => void
}

function candidateSummary(response: PersistedAllocationResponse): {
  eligible: number
  excluded: number
  topName: string | null
  budgetOk: boolean | null
} {
  const human = response.recommendation.human_requirement_result
  const budget = response.recommendation.budget_requirement_result?.budget_validation
  const eligible = human?.eligible_candidates.length ?? 0
  const excluded = human?.excluded_resources.length ?? 0
  const topName = eligible > 0 ? human!.eligible_candidates[0].name : null
  const budgetOk = budget ? budget.sufficient_balance && budget.currency_match : null
  return { eligible, excluded, topName, budgetOk }
}

export default function Agent3ProcessResultsPanel({
  processId,
  stage,
  metadataJson,
  workflowAgentResponse,
  planningBusy = false,
  planningDisabled = false,
  onPlanResources,
}: Props) {
  const [allocation, setAllocation] = useState<PersistedAllocationResponse | null>(null)

  const resolved = useMemo(() => {
    const fromWorkflow = parseProcessAgent3Allocation(workflowAgentResponse)
    if (fromWorkflow) return fromWorkflow

    const fromMeta = parseProcessAgent3Allocation(metadataJson?.agent3_allocation)
    if (fromMeta) return fromMeta

    return readStoredAgent3Allocation(processId)
  }, [workflowAgentResponse, metadataJson, processId])

  useEffect(() => {
    setAllocation(resolved)
    if (resolved) writeStoredAgent3Allocation(processId, resolved)
  }, [resolved, processId])

  const show =
    VISIBLE_STAGES.has(stage) ||
    Boolean(allocation) ||
    stage === 'DISCOVERING' ||
    stage === 'RESOURCE_PLANNING'

  if (!show) return null

  const summary = allocation ? candidateSummary(allocation) : null
  const canPlan =
    stage === 'DISCOVERING' || stage === 'RESOURCE_PLANNING' || stage === 'RISK_REVIEW'

  return (
    <Panel title="Resource Allocation">
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Agent 3 — Workforce &amp; Resource Allocation
      </p>
      <p className="mb-4 text-sm text-slate-600">
        Company Directory → Agent 3 eligibility checks → eligible employee/resource → Workflow Step → Agent 4 plan /
        approval. Agent 3 uses persisted directory identities; this UI does not invent employees or decide eligibility.
      </p>
      <p className="mb-4 text-sm">
        <Link className="link" to="/directory">
          Open Company Directory
        </Link>
      </p>

      {!allocation ? (
        <div className="space-y-3 rounded-lg border border-dashed border-slate-200 bg-slate-50/80 px-4 py-4">
          <p className="text-sm text-slate-700">
            No resource recommendation yet. Run resource planning to see ranked people,
            exclusions, budget checks, gaps, and alternatives here.
          </p>
          {onPlanResources && (stage === 'DISCOVERING' || stage === 'RESOURCE_PLANNING') ? (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={planningBusy || planningDisabled}
              onClick={onPlanResources}
            >
              {planningBusy ? 'Planning resources…' : 'Run resource planning'}
            </button>
          ) : null}
        </div>
      ) : (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-lg border border-slate-200 bg-white px-3 py-3">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                Top candidate
              </p>
              <p className="mt-1 text-sm font-semibold text-slate-900">
                {summary?.topName ?? 'None eligible'}
              </p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white px-3 py-3">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                Eligible / excluded
              </p>
              <p className="mt-1 text-sm font-semibold text-slate-900">
                {summary?.eligible ?? 0} / {summary?.excluded ?? 0}
              </p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white px-3 py-3">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                Budget check
              </p>
              <p className="mt-1 text-sm font-semibold text-slate-900">
                {summary == null || summary.budgetOk === null
                  ? 'Not requested'
                  : summary.budgetOk
                    ? 'Passed'
                    : 'Needs attention'}
              </p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white px-3 py-3">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                Confidence
              </p>
              <p className="mt-1 text-sm font-semibold text-slate-900">
                {allocation.recommendation.status === 'FAILED'
                  ? '—'
                  : allocation.recommendation.confidence ?? 'Not provided'}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Link
              to={`/agent3/recommendations/${allocation.recommendation_id}`}
              state={{ persistedResponse: allocation }}
              className="btn btn-outline btn-sm"
            >
              Open full Agent 3 page
            </Link>
            {canPlan && onPlanResources ? (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={planningBusy || planningDisabled}
                onClick={onPlanResources}
              >
                {planningBusy ? 'Re-planning…' : 'Re-run resource planning'}
              </button>
            ) : null}
          </div>

          <FullRecommendation response={allocation} embedded />
        </div>
      )}
    </Panel>
  )
}
