import { describe, expect, it } from 'vitest';
import { allocationRequestPath, getProvidedWorkflowContext, getRecommendationNavigationResponse, recommendationPath } from '../navigation/recommendationNavigation';
import { mockPersistedAllocationResponse } from './fixtures/agent3Contracts';

const processInstanceId = '00000000-0000-0000-0000-000000000004'; const taskId = '00000000-0000-0000-0000-000000000005';
describe('Agent 3 navigation', () => {
  it('exposes the allocation route', () => expect(allocationRequestPath).toBe('/agent3/allocations/new'));
  it('builds a recommendation route', () => expect(recommendationPath(taskId)).toBe(`/agent3/recommendations/${taskId}`));
  it('accepts application-supplied workflow UUIDs', () => expect(getProvidedWorkflowContext({ processInstanceId, taskId })).toEqual({ processInstanceId, taskId }));
  it('rejects absent state', () => expect(getProvidedWorkflowContext(null)).toBeNull());
  it('rejects string state', () => expect(getProvidedWorkflowContext('bad')).toBeNull());
  it('rejects a malformed process ID', () => expect(getProvidedWorkflowContext({ processInstanceId: 'bad', taskId })).toBeNull());
  it('rejects a malformed task ID', () => expect(getProvidedWorkflowContext({ processInstanceId, taskId: 'bad' })).toBeNull());
  it('ignores tenant and requester input', () => expect(getProvidedWorkflowContext({ processInstanceId, taskId, tenantId: 'attacker', requesterId: 'attacker' })).toEqual({ processInstanceId, taskId }));
});

describe('recommendation navigation state validation', () => {
  it('accepts the exact persisted response shape for the matching route', () => expect(getRecommendationNavigationResponse({ persistedResponse: mockPersistedAllocationResponse }, mockPersistedAllocationResponse.recommendation_id)).toEqual(mockPersistedAllocationResponse));
  it('rejects malformed navigation state', () => expect(getRecommendationNavigationResponse({ persistedResponse: '<script>bad</script>' }, mockPersistedAllocationResponse.recommendation_id)).toBeNull());
  it('rejects a mismatched route recommendation ID', () => expect(getRecommendationNavigationResponse({ persistedResponse: mockPersistedAllocationResponse }, '00000000-0000-0000-0000-000000000099')).toBeNull());
  it.each(['Authorization', 'accessToken', 'config'])('rejects navigation state containing %s', (key) => expect(getRecommendationNavigationResponse({ persistedResponse: { ...mockPersistedAllocationResponse, [key]: '<script>secret</script>' } }, mockPersistedAllocationResponse.recommendation_id)).toBeNull());
  it('rejects arbitrary sibling state', () => expect(getRecommendationNavigationResponse({ persistedResponse: mockPersistedAllocationResponse, html: '<img onerror=secret>' }, mockPersistedAllocationResponse.recommendation_id)).toBeNull());
});
