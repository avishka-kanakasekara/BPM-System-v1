import type { PersistedAllocationResponse } from '../types/agent3Api';
import { isValidUUID } from '../utils/metadata';
import { isPersistedAllocationResponse } from '../api/validateAgent3Response';

export const allocationRequestPath = '/agent3/allocations/new';
export const recommendationLookupPath = '/agent3/recommendations/lookup';
export const recommendationPath = (id: string) => `/agent3/recommendations/${id}`;
export interface RecommendationNavigationState { persistedResponse: PersistedAllocationResponse }

export function getProvidedWorkflowContext(state: unknown): { processInstanceId: string; taskId: string } | null {
  if (!state || typeof state !== 'object') return null;
  const value = state as Record<string, unknown>;
  return typeof value.processInstanceId === 'string' && typeof value.taskId === 'string' &&
    isValidUUID(value.processInstanceId) && isValidUUID(value.taskId)
    ? { processInstanceId: value.processInstanceId, taskId: value.taskId } : null;
}

const blockedNavigationKeys = new Set(['authorization', 'accesstoken', 'token', 'config', 'axiosconfig']);
function containsBlockedKey(value: unknown, seen = new Set<object>()): boolean {
  if (!value || typeof value !== 'object') return false;
  if (seen.has(value)) return true;
  seen.add(value);
  return Object.entries(value as Record<string, unknown>).some(([key, child]) =>
    blockedNavigationKeys.has(key.toLowerCase()) || containsBlockedKey(child, seen));
}

export function getRecommendationNavigationResponse(state: unknown, routeRecommendationId: string): PersistedAllocationResponse | null {
  if (!state || typeof state !== 'object' || Array.isArray(state)) return null;
  const entries = Object.entries(state as Record<string, unknown>);
  if (entries.length !== 1 || entries[0][0] !== 'persistedResponse' || containsBlockedKey(state)) return null;
  const response = entries[0][1];
  return isPersistedAllocationResponse(response) && response.recommendation_id === routeRecommendationId ? response : null;
}
