/**
 * Exact TypeScript contracts for Agent 3 API
 *
 * These types match the backend Pydantic schemas in:
 * - app/agents/agent3_resources/schemas.py (internal contract)
 * - app/agents/agent3_resources/api_schemas.py (API contract)
 * - app/api/v1/routes_agent3.py (endpoint contracts)
 *
 * Status values are exact backend values only:
 * - GENERATED
 * - PENDING_HUMAN_APPROVAL
 * - SUPERSEDED
 * - FAILED
 *
 * Decimal values are represented as strings to preserve precision.
 * All UUIDs are strings in TypeScript.
 */

// ============================================================================
// Message Metadata
// ============================================================================

export interface AgentMessageMetadata {
  message_id: string;
  schema_version: string;
  correlation_id: string;
  process_instance_id: string;
  task_id: string;
  tenant_id: string;
  sender: string;
  receiver: string;
  message_type: string;
  timestamp: string; // ISO-8601 with timezone
}

// ============================================================================
// Resource Requirements
// ============================================================================

export interface HumanResourceRequirement {
  resource_type: 'HUMAN';
  required_roles: string[];
  mandatory_skills: string[];
  preferred_skills: string[];
  required_authority: string | null;
  requester_id: string;
  task_deadline: string; // ISO-8601 with timezone
  estimated_effort_hours: string; // Decimal as string
  process_stage: string;
}

export interface BudgetResourceRequirement {
  resource_type: 'BUDGET';
  required_amount: string; // Decimal as string
  currency: string;
  cost_centre: string | null;
  requester_id: string;
  task_deadline: string; // ISO-8601 with timezone
  process_stage: string;
}

// ============================================================================
// Allocation Request
// ============================================================================

export interface AllocationRequest {
  metadata: AgentMessageMetadata;
  human_requirements: HumanResourceRequirement | null;
  budget_requirements: BudgetResourceRequirement | null;
}

// ============================================================================
// Score Breakdown
// ============================================================================

export interface ScoreBreakdown {
  role_match: string; // Decimal as string (0-1)
  skill_match: string; // Decimal as string (0-1)
  availability_score: string; // Decimal as string (0-1)
  workload_fit: string; // Decimal as string (0-1)
  authority_match: string; // Decimal as string (0-1)
  total_score: string; // Decimal as string (0-1)
}

// ============================================================================
// Ranked Human Candidate
// ============================================================================

export interface RankedHumanCandidate {
  resource_id: string;
  resource_type: 'HUMAN';
  name: string;
  rank: number;
  allocation_score: string; // Decimal as string (0-1)
  score_breakdown: ScoreBreakdown;
  current_workload_percentage: string; // Decimal as string (0-100)
  projected_workload_percentage: string; // Decimal as string (0-100)
  available_from: string; // ISO-8601 with timezone
  available_until: string | null; // ISO-8601 with timezone
  evidence_refs: Record<string, unknown>;
}

// ============================================================================
// Exclusion Reason Entry
// ============================================================================

export interface ExclusionReasonEntry {
  reason: string;
  description: string;
  evidence_reference: string | null;
}

// ============================================================================
// Excluded Resource
// ============================================================================

export interface ExcludedResource {
  resource_id: string;
  resource_type: string;
  name: string;
  exclusion_reasons: ExclusionReasonEntry[];
}

// ============================================================================
// Budget Validation Result
// ============================================================================

export interface BudgetValidationResult {
  resource_id: string;
  name: string;
  sufficient_balance: boolean;
  cost_centre_match: boolean;
  currency_match: boolean;
  validity_period_valid: boolean;
  within_authorization_limit: boolean;
  available_balance: string; // Decimal as string
  required_amount: string; // Decimal as string
  evidence_references: Record<string, unknown>;
}

// ============================================================================
// Requirement Result
// ============================================================================

export interface RequirementResult {
  resource_type: string;
  eligible_candidates: RankedHumanCandidate[];
  excluded_resources: ExcludedResource[];
  budget_validation: BudgetValidationResult | null;
}

// ============================================================================
// Resource Gap
// ============================================================================

export interface ResourceGap {
  gap_type: string;
  resource_type: string;
  gap_description: string;
  eligible_count: number;
  excluded_count: number;
}

// ============================================================================
// Resource Alternative
// ============================================================================

export interface ResourceAlternative {
  alternative_type: string;
  description: string;
  requires_approval: boolean;
  estimated_effort_hours: string | null; // Decimal as string
  cost_impact: string | null; // Decimal as string
}

// ============================================================================
// Allocation Recommendation (Full)
// ============================================================================

export type RecommendationStatus = 'GENERATED' | 'PENDING_HUMAN_APPROVAL' | 'SUPERSEDED' | 'FAILED';

export interface AllocationRecommendation {
  metadata: AgentMessageMetadata;
  status: RecommendationStatus;
  human_requirement_result: RequirementResult | null;
  budget_requirement_result: RequirementResult | null;
  resource_gaps: ResourceGap[];
  alternatives: ResourceAlternative[];
  explanation: string;
  requires_human_approval: boolean;
  manual_intervention_required: boolean;
  confidence: string | null; // Decimal as string (0-1)
  limitations: string[];
  error_code: string | null;
  error_message: string | null;
  retryable: boolean | null;
}

// ============================================================================
// API Response Schemas
// ============================================================================

export interface Agent3APIError {
  error_code: string;
  message: string;
  correlation_id: string | null;
  retryable: boolean;
}

export interface RecommendationSummary {
  recommendation_id: string;
  tenant_id: string;
  correlation_id: string;
  status: RecommendationStatus;
  persisted_at: string; // ISO-8601
  explanation: string;
  confidence: string | null; // Decimal as string
  requires_human_approval: boolean;
  manual_intervention_required: boolean;
  error_code: string | null;
  error_message: string | null;
  retryable: boolean | null;
}

export interface PersistedAllocationResponse {
  tenant_id: string;
  correlation_id: string;
  allocation_request_id: string;
  recommendation_id: string;
  recommendation_status: RecommendationStatus;
  persisted: true;
  persisted_at: string; // ISO-8601
  recommendation: AllocationRecommendation;
}

// ============================================================================
// FastAPI Validation Error
// ============================================================================

export interface FastAPIValidationError {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export interface FastAPIValidationErrorResponse {
  detail: FastAPIValidationError[];
}
