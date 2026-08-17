import type {
  AllocationRecommendation,
  PersistedAllocationResponse,
  RecommendationStatus,
  RecommendationSummary,
} from '../types/agent3Api';
import { isValidDecimal } from '../utils/decimalStrings';
import { isValidISO8601Timestamp } from '../utils/timestamps';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const STATUSES = new Set<RecommendationStatus>([
  'GENERATED', 'PENDING_HUMAN_APPROVAL', 'SUPERSEDED', 'FAILED',
]);
const object = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
const string = (value: unknown): value is string => typeof value === 'string';
const nullableString = (value: unknown): value is string | null => value === null || string(value);
const nullableBoolean = (value: unknown): value is boolean | null => value === null || typeof value === 'boolean';
const uuid = (value: unknown): value is string => string(value) && UUID.test(value);
const timestamp = (value: unknown): value is string => string(value) && isValidISO8601Timestamp(value);
const decimal = (value: unknown): value is string => string(value) && isValidDecimal(value);
const nullableDecimal = (value: unknown): value is string | null => value === null || decimal(value);
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(string);
const status = (value: unknown): value is RecommendationStatus => string(value) && STATUSES.has(value as RecommendationStatus);

function metadata(value: unknown): boolean {
  return object(value) && uuid(value.message_id) && string(value.schema_version) &&
    uuid(value.correlation_id) && uuid(value.process_instance_id) && uuid(value.task_id) &&
    uuid(value.tenant_id) && string(value.sender) && string(value.receiver) &&
    string(value.message_type) && timestamp(value.timestamp);
}

function scoreBreakdown(value: unknown): boolean {
  return object(value) && ['role_match', 'skill_match', 'availability_score', 'workload_fit', 'authority_match', 'total_score']
    .every((key) => decimal(value[key]));
}

function candidate(value: unknown): boolean {
  return object(value) && uuid(value.resource_id) && value.resource_type === 'HUMAN' &&
    string(value.name) && Number.isInteger(value.rank) && decimal(value.allocation_score) &&
    scoreBreakdown(value.score_breakdown) && decimal(value.current_workload_percentage) &&
    decimal(value.projected_workload_percentage) && timestamp(value.available_from) &&
    (value.available_until === null || timestamp(value.available_until)) && object(value.evidence_refs);
}

function excluded(value: unknown): boolean {
  return object(value) && uuid(value.resource_id) && string(value.resource_type) && string(value.name) &&
    Array.isArray(value.exclusion_reasons) && value.exclusion_reasons.every((reason) =>
      object(reason) && string(reason.reason) && string(reason.description) && nullableString(reason.evidence_reference));
}

function budget(value: unknown): boolean {
  return object(value) && uuid(value.resource_id) && string(value.name) &&
    ['sufficient_balance', 'cost_centre_match', 'currency_match', 'validity_period_valid', 'within_authorization_limit']
      .every((key) => typeof value[key] === 'boolean') &&
    decimal(value.available_balance) && decimal(value.required_amount) && object(value.evidence_references);
}

function requirement(value: unknown): boolean {
  return object(value) && string(value.resource_type) && Array.isArray(value.eligible_candidates) &&
    value.eligible_candidates.every(candidate) && Array.isArray(value.excluded_resources) &&
    value.excluded_resources.every(excluded) && (value.budget_validation === null || budget(value.budget_validation));
}

export function isAllocationRecommendation(value: unknown): value is AllocationRecommendation {
  return object(value) && metadata(value.metadata) && status(value.status) &&
    (value.human_requirement_result === null || requirement(value.human_requirement_result)) &&
    (value.budget_requirement_result === null || requirement(value.budget_requirement_result)) &&
    Array.isArray(value.resource_gaps) && value.resource_gaps.every((gap) => object(gap) &&
      string(gap.gap_type) && string(gap.resource_type) && string(gap.gap_description) &&
      Number.isInteger(gap.eligible_count) && Number.isInteger(gap.excluded_count)) &&
    Array.isArray(value.alternatives) && value.alternatives.every((alternative) => object(alternative) &&
      string(alternative.alternative_type) && string(alternative.description) &&
      typeof alternative.requires_approval === 'boolean' &&
      nullableDecimal(alternative.estimated_effort_hours) && nullableDecimal(alternative.cost_impact)) &&
    string(value.explanation) && typeof value.requires_human_approval === 'boolean' &&
    typeof value.manual_intervention_required === 'boolean' && nullableDecimal(value.confidence) &&
    strings(value.limitations) && nullableString(value.error_code) && nullableString(value.error_message) &&
    nullableBoolean(value.retryable);
}

export function isRecommendationSummary(value: unknown): value is RecommendationSummary {
  return object(value) && uuid(value.recommendation_id) && uuid(value.tenant_id) &&
    uuid(value.correlation_id) && status(value.status) && timestamp(value.persisted_at) &&
    string(value.explanation) && nullableDecimal(value.confidence) &&
    typeof value.requires_human_approval === 'boolean' &&
    typeof value.manual_intervention_required === 'boolean' && nullableString(value.error_code) &&
    nullableString(value.error_message) && nullableBoolean(value.retryable);
}

export function isPersistedAllocationResponse(value: unknown): value is PersistedAllocationResponse {
  return object(value) && uuid(value.tenant_id) && uuid(value.correlation_id) &&
    uuid(value.allocation_request_id) && uuid(value.recommendation_id) &&
    status(value.recommendation_status) && value.persisted === true && timestamp(value.persisted_at) &&
    isAllocationRecommendation(value.recommendation);
}
