/**
 * Agent 3 API Client Functions
 *
 * These functions implement the exact Agent 3 API endpoints:
 * - POST /api/v1/agent3/allocations
 * - GET /api/v1/agent3/recommendations/{recommendation_id}
 * - GET /api/v1/agent3/recommendations/by-correlation/{correlation_id}
 *
 * All functions use the shared Axios client with bearer token authentication.
 * UUID validation is performed before sending requests.
 * Decimal values are serialized as strings.
 */

import apiClient from '../../../services/apiClient';
import type { 
  AllocationRequest, 
  PersistedAllocationResponse, 
  RecommendationSummary 
} from '../types/agent3Api';
import { normalizeAgent3Error } from './normalizeAgent3Error';
import { getAgent3Session } from '../auth/agent3Session';
import { isPersistedAllocationResponse, isRecommendationSummary } from './validateAgent3Response';

// ============================================================================
// UUID Validation
// ============================================================================

function isValidUUID(uuid: string): boolean {
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  return uuidRegex.test(uuid);
}

// ============================================================================
// API Client Functions
// ============================================================================

/**
 * Submit an allocation request to Agent 3.
 *
 * POST /api/v1/agent3/allocations
 *
 * @param request - The allocation request with metadata and requirements
 * @returns Promise resolving to the persisted allocation response
 * @throws Agent3ClientError for API errors
 */
export async function submitAllocationRequest(
  request: AllocationRequest
): Promise<PersistedAllocationResponse> {
  try {
    const session = await getAgent3Session();
    if (request.metadata.tenant_id !== session.tenantId ||
        (request.human_requirements?.requester_id !== undefined && request.human_requirements.requester_id !== session.requesterId) ||
        (request.budget_requirements?.requester_id !== undefined && request.budget_requirements.requester_id !== session.requesterId)) {
      throw new Error('Authenticated context does not match request metadata');
    }
    const response = await apiClient.post<unknown>(
      '/api/v1/agent3/allocations',
      request,
      { headers: { Authorization: `Bearer ${session.accessToken}` } },
    );
    if (!isPersistedAllocationResponse(response.data)) throw new Error('Invalid response contract');
    return response.data;
  } catch (error) {
    throw normalizeAgent3Error(error);
  }
}

/**
 * Get a recommendation by its ID.
 *
 * GET /api/v1/agent3/recommendations/{recommendation_id}
 *
 * @param recommendationId - The recommendation UUID
 * @returns Promise resolving to the recommendation summary
 * @throws Agent3ClientError for API errors or invalid UUID
 */
export async function getRecommendationById(
  recommendationId: string
): Promise<RecommendationSummary> {
  // Validate UUID before sending request
  if (!isValidUUID(recommendationId)) {
    throw {
      kind: 'validation' as const,
      status: null,
      errorCode: 'INVALID_UUID',
      message: 'Invalid recommendation ID format',
      retryable: false
    };
  }

  try {
    const session = await getAgent3Session();
    const response = await apiClient.get<unknown>(
      `/api/v1/agent3/recommendations/${recommendationId}`,
      { headers: { Authorization: `Bearer ${session.accessToken}` } },
    );
    if (!isRecommendationSummary(response.data)) throw new Error('Invalid response contract');
    return response.data;
  } catch (error) {
    throw normalizeAgent3Error(error);
  }
}

/**
 * Get the latest recommendation by correlation ID.
 *
 * GET /api/v1/agent3/recommendations/by-correlation/{correlation_id}
 *
 * @param correlationId - The correlation UUID
 * @returns Promise resolving to the recommendation summary
 * @throws Agent3ClientError for API errors or invalid UUID
 */
export async function getRecommendationByCorrelationId(
  correlationId: string
): Promise<RecommendationSummary> {
  // Validate UUID before sending request
  if (!isValidUUID(correlationId)) {
    throw {
      kind: 'validation' as const,
      status: null,
      errorCode: 'INVALID_UUID',
      message: 'Invalid correlation ID format',
      retryable: false
    };
  }

  try {
    const session = await getAgent3Session();
    const response = await apiClient.get<unknown>(
      `/api/v1/agent3/recommendations/by-correlation/${correlationId}`,
      { headers: { Authorization: `Bearer ${session.accessToken}` } },
    );
    if (!isRecommendationSummary(response.data)) throw new Error('Invalid response contract');
    return response.data;
  } catch (error) {
    throw normalizeAgent3Error(error);
  }
}
