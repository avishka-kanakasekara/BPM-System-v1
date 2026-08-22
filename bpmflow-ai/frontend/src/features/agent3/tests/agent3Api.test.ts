import { AxiosError } from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getRecommendationByCorrelationId, getRecommendationById, submitAllocationRequest } from '../api/agent3Api';
import { normalizeAgent3Error } from '../api/normalizeAgent3Error';
import { MOCK_CORRELATION_ID, MOCK_RECOMMENDATION_ID, MOCK_REQUESTER_ID, MOCK_TENANT_ID, mockAllocationRequest, mockPersistedAllocationResponse, mockRecommendationSummary } from './fixtures/agent3Contracts';

vi.mock('../../../services/apiClient', () => ({ default: { post: vi.fn(), get: vi.fn() } }));
vi.mock('../auth/agent3Session', () => ({ getAgent3Session: vi.fn() }));
import apiClient from '../../../services/apiClient';
import { getAgent3Session } from '../auth/agent3Session';

const session = (accessToken = 'clearly-fake-access-token') => ({ accessToken, requesterId: MOCK_REQUESTER_ID, tenantId: MOCK_TENANT_ID });
const malformedError = { kind: 'unexpected', errorCode: 'UNKNOWN_ERROR', message: 'An unexpected error occurred' };

describe('Agent 3 API runtime boundary', () => {
  beforeEach(() => { vi.clearAllMocks(); vi.mocked(getAgent3Session).mockResolvedValue(session()); });

  it('submits with one request-scoped authenticated context and validates the full result', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: mockPersistedAllocationResponse });
    await expect(submitAllocationRequest(mockAllocationRequest)).resolves.toEqual(mockPersistedAllocationResponse);
    expect(apiClient.post).toHaveBeenCalledWith('/api/v1/agent3/allocations', mockAllocationRequest, { headers: { Authorization: 'Bearer clearly-fake-access-token' } });
  });

  it('preserves Decimal strings exactly through request and response transport', async () => {
    const request = structuredClone(mockAllocationRequest);
    if (request.budget_requirements) request.budget_requirements.required_amount = '12000.00';
    if (request.human_requirements) request.human_requirements.estimated_effort_hours = '9999999999999999.99';
    const response = structuredClone(mockPersistedAllocationResponse);
    response.recommendation.confidence = '0.8750';
    vi.mocked(apiClient.post).mockResolvedValue({ data: response });
    const result = await submitAllocationRequest(request);
    expect(vi.mocked(apiClient.post).mock.calls[0][1]).toEqual(request);
    expect(result.recommendation.confidence).toBe('0.8750');
    expect(request.budget_requirements?.required_amount).toBe('12000.00');
    expect(request.human_requirements?.estimated_effort_hours).toBe('9999999999999999.99');
  });

  it('uses refreshed tokens on sequential requests', async () => {
    vi.mocked(getAgent3Session).mockResolvedValueOnce(session('clearly-fake-token-one')).mockResolvedValueOnce(session('clearly-fake-token-two'));
    vi.mocked(apiClient.get).mockResolvedValue({ data: mockRecommendationSummary });
    await getRecommendationById(MOCK_RECOMMENDATION_ID); await getRecommendationById(MOCK_RECOMMENDATION_ID);
    expect(vi.mocked(apiClient.get).mock.calls.map((call) => call[1]?.headers?.Authorization)).toEqual(['Bearer clearly-fake-token-one', 'Bearer clearly-fake-token-two']);
  });

  it('fails closed when POST metadata differs from its session snapshot', async () => {
    const request = structuredClone(mockAllocationRequest); request.metadata.tenant_id = '00000000-0000-0000-0000-000000000099';
    await expect(submitAllocationRequest(request)).rejects.toMatchObject(malformedError);
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it.each([
    ['malformed UUID', { ...mockPersistedAllocationResponse, recommendation_id: 'bad' }],
    ['APPROVED status', { ...mockPersistedAllocationResponse, recommendation_status: 'APPROVED' }],
    ['persisted false', { ...mockPersistedAllocationResponse, persisted: false }],
    ['missing field', (() => { const value = structuredClone(mockPersistedAllocationResponse) as unknown as Record<string, unknown>; delete value.tenant_id; return value; })()],
    ['numeric Decimal', { ...mockPersistedAllocationResponse, recommendation: { ...mockPersistedAllocationResponse.recommendation, confidence: 0.875 } }],
    ['naive timestamp', { ...mockPersistedAllocationResponse, persisted_at: '2026-01-01T12:00:00' }],
    ['malformed recommendation', { ...mockPersistedAllocationResponse, recommendation: {} }],
    ['HTML body', '<html>secret</html>'],
  ])('rejects malformed POST response: %s', async (_name, data) => {
    vi.mocked(apiClient.post).mockResolvedValue({ data });
    await expect(submitAllocationRequest(mockAllocationRequest)).rejects.toMatchObject(malformedError);
  });

  it.each([
    ['malformed UUID', { ...mockRecommendationSummary, recommendation_id: 'bad' }],
    ['APPROVED status', { ...mockRecommendationSummary, status: 'APPROVED' }],
    ['numeric Decimal', { ...mockRecommendationSummary, confidence: 0.875 }],
    ['naive timestamp', { ...mockRecommendationSummary, persisted_at: '2026-01-01T12:00:00' }],
    ['missing field', (() => { const value = structuredClone(mockRecommendationSummary) as unknown as Record<string, unknown>; delete value.explanation; return value; })()],
    ['string body', 'not-json'],
  ])('rejects malformed summary response: %s', async (_name, data) => {
    vi.mocked(apiClient.get).mockResolvedValue({ data });
    await expect(getRecommendationById(MOCK_RECOMMENDATION_ID)).rejects.toMatchObject(malformedError);
  });

  it('validates IDs before session or network access', async () => {
    await expect(getRecommendationById('invalid')).rejects.toMatchObject({ kind: 'validation', errorCode: 'INVALID_UUID' });
    await expect(getRecommendationByCorrelationId('invalid')).rejects.toMatchObject({ kind: 'validation', errorCode: 'INVALID_UUID' });
    expect(getAgent3Session).not.toHaveBeenCalled(); expect(apiClient.get).not.toHaveBeenCalled();
  });

  it('validates both summary routes', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: mockRecommendationSummary });
    await expect(getRecommendationById(MOCK_RECOMMENDATION_ID)).resolves.toEqual(mockRecommendationSummary);
    await expect(getRecommendationByCorrelationId(MOCK_CORRELATION_ID)).resolves.toEqual(mockRecommendationSummary);
  });
});

function axiosError(status: number, data: unknown): AxiosError {
  return new AxiosError('hostile raw error', undefined, undefined, undefined, { status, data } as never);
}

describe('safe error normalization', () => {
  it.each([[401, 'authentication'], [403, 'authorization'], [404, 'not_found'], [409, 'conflict'], [422, 'validation'], [500, 'unexpected'], [503, 'unavailable']] as const)(
    'maps %i to %s without copying hostile detail', (status, kind) => {
      const hostile = 'Bearer clearly-fake-secret postgresql://user:password@db/x SELECT * FROM users <script>x</script> stack trace';
      const result = normalizeAgent3Error(axiosError(status, { detail: { error_code: 'INTERNAL_ERROR', message: hostile, retryable: false } }));
      expect(result.kind).toBe(kind); expect(JSON.stringify(result)).not.toContain(hostile); expect(JSON.stringify(result)).not.toContain('password');
    });

  it('sanitizes FastAPI field errors', () => {
    const result = normalizeAgent3Error(axiosError(422, { detail: [{ loc: ['body', 'metadata', 'tenant_id'], msg: '<script>password</script>', type: 'value_error' }] }));
    expect(result.fieldErrors).toEqual({ tenant_id: ['Invalid value'] });
  });

  it('normalizes missing and cross-tenant 404s identically', () => {
    const missing = normalizeAgent3Error(axiosError(404, { detail: { error_code: 'RECOMMENDATION_NOT_FOUND', message: 'missing', retryable: false } }));
    const crossTenant = normalizeAgent3Error(axiosError(404, { detail: { error_code: 'RECOMMENDATION_NOT_FOUND', message: 'cross tenant', retryable: false } }));
    expect(crossTenant).toEqual(missing);
  });
});
