/**
 * Coerce Agent 3 allocation payloads from workflow responses / process metadata
 * into PersistedAllocationResponse for the process detail UI.
 *
 * Backend Decimal / float serialization can vary; we normalize numbers to
 * decimal strings so the existing Agent 3 presentation components can render.
 */

import type {
  AllocationRecommendation,
  PersistedAllocationResponse,
  RecommendationStatus,
} from '../../features/agent3/types/agent3Api'
import { isPersistedAllocationResponse } from '../../features/agent3/api/validateAgent3Response'

const STATUSES = new Set<RecommendationStatus>([
  'GENERATED',
  'PENDING_HUMAN_APPROVAL',
  'SUPERSEDED',
  'FAILED',
])

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function decimalish(value: unknown): string | null {
  if (typeof value === 'string' && /^\d+(\.\d+)?$/.test(value.trim())) return value.trim()
  if (typeof value === 'number' && Number.isFinite(value) && value >= 0) {
    // Avoid binary float noise for display; keep a stable string form.
    return String(value)
  }
  return null
}

function nullableDecimalish(value: unknown): string | null {
  if (value === null || value === undefined) return null
  return decimalish(value)
}

function normalizeScoreBreakdown(raw: unknown): Record<string, string> | null {
  const obj = asRecord(raw)
  if (!obj) return null
  const keys = [
    'role_match',
    'skill_match',
    'availability_score',
    'workload_fit',
    'authority_match',
    'total_score',
  ] as const
  const out: Record<string, string> = {}
  for (const key of keys) {
    const d = decimalish(obj[key])
    if (d === null) return null
    out[key] = d
  }
  return out
}

function normalizeCandidate(raw: unknown): Record<string, unknown> | null {
  const obj = asRecord(raw)
  if (!obj) return null
  const score = normalizeScoreBreakdown(obj.score_breakdown)
  const allocationScore = decimalish(obj.allocation_score)
  const current = decimalish(obj.current_workload_percentage)
  const projected = decimalish(obj.projected_workload_percentage)
  if (!score || allocationScore === null || current === null || projected === null) return null
  return {
    ...obj,
    allocation_score: allocationScore,
    current_workload_percentage: current,
    projected_workload_percentage: projected,
    score_breakdown: score,
    evidence_refs: asRecord(obj.evidence_refs) ?? {},
  }
}

function normalizeBudget(raw: unknown): Record<string, unknown> | null {
  if (raw === null) return null
  const obj = asRecord(raw)
  if (!obj) return null
  const available = decimalish(obj.available_balance)
  const required = decimalish(obj.required_amount)
  if (available === null || required === null) return null
  return {
    ...obj,
    available_balance: available,
    required_amount: required,
    evidence_references: asRecord(obj.evidence_references) ?? {},
  }
}

function normalizeRequirement(raw: unknown): Record<string, unknown> | null {
  if (raw === null) return null
  const obj = asRecord(raw)
  if (!obj) return null
  const candidates = Array.isArray(obj.eligible_candidates)
    ? obj.eligible_candidates.map(normalizeCandidate).filter(Boolean)
    : []
  const excluded = Array.isArray(obj.excluded_resources) ? obj.excluded_resources : []
  return {
    ...obj,
    eligible_candidates: candidates,
    excluded_resources: excluded,
    budget_validation: obj.budget_validation == null ? null : normalizeBudget(obj.budget_validation),
  }
}

function normalizeRecommendation(raw: unknown): AllocationRecommendation | null {
  const obj = asRecord(raw)
  if (!obj) return null
  const status = obj.status
  if (typeof status !== 'string' || !STATUSES.has(status as RecommendationStatus)) return null
  if (typeof obj.explanation !== 'string') return null
  if (typeof obj.requires_human_approval !== 'boolean') return null
  if (typeof obj.manual_intervention_required !== 'boolean') return null

  const confidence = nullableDecimalish(obj.confidence)
  const alternatives = Array.isArray(obj.alternatives)
    ? obj.alternatives.map((alt) => {
        const a = asRecord(alt)
        if (!a) return null
        return {
          ...a,
          estimated_effort_hours: nullableDecimalish(a.estimated_effort_hours),
          cost_impact: nullableDecimalish(a.cost_impact),
        }
      }).filter(Boolean)
    : []

  return {
    ...(obj as unknown as AllocationRecommendation),
    status: status as RecommendationStatus,
    confidence,
    human_requirement_result: normalizeRequirement(obj.human_requirement_result) as AllocationRecommendation['human_requirement_result'],
    budget_requirement_result: normalizeRequirement(obj.budget_requirement_result) as AllocationRecommendation['budget_requirement_result'],
    resource_gaps: Array.isArray(obj.resource_gaps) ? (obj.resource_gaps as AllocationRecommendation['resource_gaps']) : [],
    alternatives: alternatives as AllocationRecommendation['alternatives'],
    limitations: Array.isArray(obj.limitations)
      ? obj.limitations.filter((x): x is string => typeof x === 'string')
      : [],
    error_code: typeof obj.error_code === 'string' || obj.error_code === null ? obj.error_code : null,
    error_message:
      typeof obj.error_message === 'string' || obj.error_message === null ? obj.error_message : null,
    retryable: typeof obj.retryable === 'boolean' || obj.retryable === null ? obj.retryable : null,
  }
}

/** Normalize workflow / metadata payloads into a renderable Agent 3 response. */
export function parseProcessAgent3Allocation(value: unknown): PersistedAllocationResponse | null {
  if (isPersistedAllocationResponse(value)) return value

  const obj = asRecord(value)
  if (!obj) return null

  // Nested under agent3_allocation already unwrapped by callers, but accept either.
  const nested = asRecord(obj.agent3_allocation)
  if (nested) return parseProcessAgent3Allocation(nested)

  const recommendation = normalizeRecommendation(obj.recommendation)
  if (!recommendation) return null

  const recommendationStatus = obj.recommendation_status
  if (
    typeof recommendationStatus !== 'string' ||
    !STATUSES.has(recommendationStatus as RecommendationStatus)
  ) {
    return null
  }

  const tenantId = typeof obj.tenant_id === 'string' ? obj.tenant_id : null
  const correlationId = typeof obj.correlation_id === 'string' ? obj.correlation_id : null
  const allocationRequestId =
    typeof obj.allocation_request_id === 'string' ? obj.allocation_request_id : null
  const recommendationId =
    typeof obj.recommendation_id === 'string' ? obj.recommendation_id : null
  const persistedAt = typeof obj.persisted_at === 'string' ? obj.persisted_at : null

  if (!tenantId || !correlationId || !allocationRequestId || !recommendationId || !persistedAt) {
    return null
  }

  return {
    tenant_id: tenantId,
    correlation_id: correlationId,
    allocation_request_id: allocationRequestId,
    recommendation_id: recommendationId,
    recommendation_status: recommendationStatus as RecommendationStatus,
    persisted: true,
    persisted_at: persistedAt,
    recommendation,
  }
}

export function storageKeyForAgent3(processId: string): string {
  return `bpmflow:agent3_allocation:${processId}`
}

export function readStoredAgent3Allocation(processId: string): PersistedAllocationResponse | null {
  if (!processId || typeof sessionStorage === 'undefined') return null
  try {
    const raw = sessionStorage.getItem(storageKeyForAgent3(processId))
    if (!raw) return null
    return parseProcessAgent3Allocation(JSON.parse(raw))
  } catch {
    return null
  }
}

export function writeStoredAgent3Allocation(
  processId: string,
  value: PersistedAllocationResponse,
): void {
  if (!processId || typeof sessionStorage === 'undefined') return
  try {
    sessionStorage.setItem(storageKeyForAgent3(processId), JSON.stringify(value))
  } catch {
    // ignore quota / private mode
  }
}
