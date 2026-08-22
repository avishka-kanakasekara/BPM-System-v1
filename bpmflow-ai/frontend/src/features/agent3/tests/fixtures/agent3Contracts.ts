/**
 * Agent 3 Contract Test Fixtures
 *
 * These fixtures provide sample data for testing Agent 3 API contracts.
 * They match the exact backend schema structure.
 */

import type {
  AllocationRequest,
  AgentMessageMetadata,
  HumanResourceRequirement,
  BudgetResourceRequirement,
  RecommendationSummary,
  PersistedAllocationResponse,
  AllocationRecommendation,
  Agent3APIError,
  FastAPIValidationErrorResponse
} from '../../types/agent3Api';

// ============================================================================
// UUID Constants
// ============================================================================

export const MOCK_TENANT_ID = '00000000-0000-0000-0000-000000000001';
export const MOCK_REQUESTER_ID = '00000000-0000-0000-0000-000000000002';
export const MOCK_CORRELATION_ID = '00000000-0000-0000-0000-000000000003';
export const MOCK_PROCESS_INSTANCE_ID = '00000000-0000-0000-0000-000000000004';
export const MOCK_TASK_ID = '00000000-0000-0000-0000-000000000005';
export const MOCK_RECOMMENDATION_ID = '00000000-0000-0000-0000-000000000006';
export const MOCK_ALLOCATION_REQUEST_ID = '00000000-0000-0000-0000-000000000007';

// ============================================================================
// Message Metadata Fixture
// ============================================================================

export const mockAgentMessageMetadata: AgentMessageMetadata = {
  message_id: '00000000-0000-0000-0000-000000000008',
  schema_version: '1.0.0',
  correlation_id: MOCK_CORRELATION_ID,
  process_instance_id: MOCK_PROCESS_INSTANCE_ID,
  task_id: MOCK_TASK_ID,
  tenant_id: MOCK_TENANT_ID,
  sender: 'agent3',
  receiver: 'agent4',
  message_type: 'RESOURCE_ALLOCATION_REQUEST',
  timestamp: '2026-01-01T12:00:00Z'
};

// ============================================================================
// Human Resource Requirement Fixture
// ============================================================================

export const mockHumanResourceRequirement: HumanResourceRequirement = {
  resource_type: 'HUMAN',
  required_roles: ['developer'],
  mandatory_skills: ['python', 'fastapi'],
  preferred_skills: ['typescript'],
  required_authority: 'senior',
  requester_id: MOCK_REQUESTER_ID,
  task_deadline: '2026-12-31T23:59:59Z',
  estimated_effort_hours: '8.0',
  process_stage: 'resource_allocation'
};

// ============================================================================
// Budget Resource Requirement Fixture
// ============================================================================

export const mockBudgetResourceRequirement: BudgetResourceRequirement = {
  resource_type: 'BUDGET',
  required_amount: '1000.00',
  currency: 'USD',
  cost_centre: 'CC-DEMO',
  requester_id: MOCK_REQUESTER_ID,
  task_deadline: '2026-12-31T23:59:59Z',
  process_stage: 'resource_allocation'
};

// ============================================================================
// Allocation Request Fixture
// ============================================================================

export const mockAllocationRequest: AllocationRequest = {
  metadata: mockAgentMessageMetadata,
  human_requirements: mockHumanResourceRequirement,
  budget_requirements: mockBudgetResourceRequirement
};

// ============================================================================
// Recommendation Summary Fixture
// ============================================================================

export const mockRecommendationSummary: RecommendationSummary = {
  recommendation_id: MOCK_RECOMMENDATION_ID,
  tenant_id: MOCK_TENANT_ID,
  correlation_id: MOCK_CORRELATION_ID,
  status: 'PENDING_HUMAN_APPROVAL',
  persisted_at: '2026-01-01T12:00:00Z',
  explanation: 'Test recommendation explanation',
  confidence: '0.85',
  requires_human_approval: true,
  manual_intervention_required: false,
  error_code: null,
  error_message: null,
  retryable: null
};

// ============================================================================
// Persisted Allocation Response Fixture
// ============================================================================

// ============================================================================
// Agent 3 API Error Fixture
// ============================================================================

export const mockAgent3APIError: Agent3APIError = {
  error_code: 'TENANT_MISMATCH',
  message: 'Request tenant_id does not match authenticated tenant',
  correlation_id: MOCK_CORRELATION_ID,
  retryable: false
};

// ============================================================================
// FastAPI Validation Error Fixture
// ============================================================================

export const mockFastAPIValidationErrorResponse: FastAPIValidationErrorResponse = {
  detail: [
    {
      loc: ['body', 'metadata', 'tenant_id'],
      msg: 'field required',
      type: 'value_error.missing'
    }
  ]
};

// ============================================================================
// Allocation Recommendation Fixture (Full)
// ============================================================================

export const mockAllocationRecommendation: AllocationRecommendation = {
  metadata: mockAgentMessageMetadata,
  status: 'PENDING_HUMAN_APPROVAL',
  human_requirement_result: null,
  budget_requirement_result: null,
  resource_gaps: [],
  alternatives: [],
  explanation: 'Test explanation',
  requires_human_approval: true,
  manual_intervention_required: false,
  confidence: '0.85',
  limitations: [],
  error_code: null,
  error_message: null,
  retryable: null
};

export const mockPersistedAllocationResponse: PersistedAllocationResponse = {
  tenant_id: MOCK_TENANT_ID,
  correlation_id: MOCK_CORRELATION_ID,
  allocation_request_id: MOCK_ALLOCATION_REQUEST_ID,
  recommendation_id: MOCK_RECOMMENDATION_ID,
  recommendation_status: 'PENDING_HUMAN_APPROVAL',
  persisted: true,
  persisted_at: '2026-01-01T12:00:00Z',
  recommendation: mockAllocationRecommendation
};
