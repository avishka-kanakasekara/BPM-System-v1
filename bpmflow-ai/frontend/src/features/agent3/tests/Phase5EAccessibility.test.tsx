import axe from 'axe-core';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getRecommendationById } from '../api/agent3Api';
import { getAgent3Session } from '../auth/agent3Session';
import { Agent3ErrorBoundary } from '../components/Agent3ErrorBoundary';
import { Agent3SectionNavigation } from '../components/Agent3SectionNavigation';
import { FullRecommendation, RecommendationErrorState, RecommendationLoadingState, SummaryRecommendation } from '../components/RecommendationPresentation';
import AllocationRequestPage from '../pages/AllocationRequestPage';
import RecommendationLookupPage from '../pages/RecommendationLookupPage';
import type { PersistedAllocationResponse } from '../types/agent3Api';
import { MOCK_RECOMMENDATION_ID, MOCK_REQUESTER_ID, MOCK_TENANT_ID, mockPersistedAllocationResponse, mockRecommendationSummary } from './fixtures/agent3Contracts';

vi.mock('../auth/agent3Session', () => ({ getAgent3Session: vi.fn() }));
vi.mock('../api/agent3Api', () => ({ submitAllocationRequest: vi.fn(), getRecommendationById: vi.fn(), getRecommendationByCorrelationId: vi.fn() }));

const session = { requesterId: MOCK_REQUESTER_ID, tenantId: MOCK_TENANT_ID, accessToken: 'fake-test-token' };
const renderAt = (node: React.ReactNode, path = '/agent3/allocations/new') => render(<MemoryRouter initialEntries={[path]}>{node}</MemoryRouter>);
async function expectNoAxeViolations(container: HTMLElement) {
  const result = await axe.run(container);
  expect(result.violations, result.violations.map(({ id, help }) => `${id}: ${help}`).join('\n')).toEqual([]);
}
async function allocation() {
  const view = renderAt(<AllocationRequestPage />);
  await screen.findByRole('heading', { name: 'Create allocation request' });
  return view;
}

const human: PersistedAllocationResponse = structuredClone(mockPersistedAllocationResponse);
human.recommendation.human_requirement_result = { resource_type: 'HUMAN', eligible_candidates: [], excluded_resources: [], budget_validation: null };
const budget: PersistedAllocationResponse = structuredClone(mockPersistedAllocationResponse);
budget.recommendation.budget_requirement_result = { resource_type: 'BUDGET', eligible_candidates: [], excluded_resources: [], budget_validation: { resource_id: '00000000-0000-0000-0000-000000000020', name: 'Approved budget', sufficient_balance: true, cost_centre_match: true, currency_match: true, validity_period_valid: true, within_authorization_limit: true, available_balance: '1000.00', required_amount: '50.25', evidence_references: {} } };
const mixed: PersistedAllocationResponse = structuredClone(human);
mixed.recommendation.budget_requirement_result = budget.recommendation.budget_requirement_result;
const failed: PersistedAllocationResponse = structuredClone(mockPersistedAllocationResponse);
failed.recommendation_status = 'FAILED'; failed.recommendation.status = 'FAILED'; failed.recommendation.error_code = 'SAFE_FAILURE'; failed.recommendation.retryable = false; failed.recommendation.manual_intervention_required = true;

function ThrowingChild(): never { throw new Error('Bearer hostile-secret postgresql://password@host/db'); }

describe('Phase 5E direct axe checks', () => {
  beforeEach(() => { vi.clearAllMocks(); vi.mocked(getAgent3Session).mockResolvedValue(session); vi.mocked(getRecommendationById).mockResolvedValue(mockRecommendationSummary); });
  it('has no violations in the valid allocation page', async () => { const { container } = await allocation(); await expectNoAxeViolations(container); });
  it('has no violations in the HUMAN form', async () => { const { container } = await allocation(); expect(screen.getByRole('radio', { name: 'Human' })).toBeChecked(); await expectNoAxeViolations(container); });
  it('has no violations in the BUDGET form', async () => { const user = userEvent.setup(); const { container } = await allocation(); await user.click(screen.getByRole('radio', { name: 'Budget' })); await expectNoAxeViolations(container); });
  it('has no violations in the mixed form', async () => { const user = userEvent.setup(); const { container } = await allocation(); await user.click(screen.getByRole('radio', { name: 'Human + Budget' })); await expectNoAxeViolations(container); });
  it('has no violations in form validation errors', async () => { const user = userEvent.setup(); const { container } = await allocation(); await user.click(screen.getByRole('button', { name: 'Submit allocation request' })); await screen.findByRole('alert'); await expectNoAxeViolations(container); });
  it('has no violations in a full HUMAN result', async () => { const { container } = render(<FullRecommendation response={human} />); await expectNoAxeViolations(container); });
  it('has no violations in a full BUDGET result', async () => { const { container } = render(<FullRecommendation response={budget} />); await expectNoAxeViolations(container); });
  it('has no violations in a mixed result', async () => { const { container } = render(<FullRecommendation response={mixed} />); await expectNoAxeViolations(container); });
  it('has no violations in a technical FAILED result', async () => { const { container } = render(<FullRecommendation response={failed} />); await expectNoAxeViolations(container); });
  it('has no violations in a summary result', async () => { const { container } = render(<SummaryRecommendation summary={mockRecommendationSummary} />); await expectNoAxeViolations(container); });
  it('has no violations in the lookup initial state', async () => { const { container } = renderAt(<RecommendationLookupPage />, '/agent3/recommendations/lookup'); await expectNoAxeViolations(container); });
  it('has no violations in lookup success', async () => { const user = userEvent.setup(); const { container } = renderAt(<RecommendationLookupPage />, '/agent3/recommendations/lookup'); await user.type(screen.getByLabelText('Recommendation ID'), MOCK_RECOMMENDATION_ID); await user.click(screen.getByRole('button', { name: 'Find recommendation' })); await screen.findByText('Summary view'); await expectNoAxeViolations(container); });
  it('has no violations in a lookup error', async () => { vi.mocked(getRecommendationById).mockRejectedValue({ kind: 'not_found', retryable: false }); const user = userEvent.setup(); const { container } = renderAt(<RecommendationLookupPage />, '/agent3/recommendations/lookup'); await user.type(screen.getByLabelText('Recommendation ID'), MOCK_RECOMMENDATION_ID); await user.click(screen.getByRole('button', { name: 'Find recommendation' })); await screen.findByRole('alert'); await expectNoAxeViolations(container); });
  it('has no violations in the feature error boundary', async () => { vi.spyOn(console, 'error').mockImplementation(() => undefined); const { container } = renderAt(<Agent3ErrorBoundary><ThrowingChild /></Agent3ErrorBoundary>); await expectNoAxeViolations(container); });
});

describe('Phase 5E integration and accessibility regression coverage', () => {
  beforeEach(() => { vi.clearAllMocks(); vi.mocked(getAgent3Session).mockResolvedValue(session); });
  it('labels the Agent 3 navigation landmark', () => { renderAt(<Agent3SectionNavigation />); expect(screen.getByRole('navigation', { name: 'Agent 3 section navigation' })).toBeInTheDocument(); });
  it('marks only the exact active navigation link', () => { renderAt(<Agent3SectionNavigation />); expect(screen.getByRole('link', { name: /New Allocation/ })).toHaveAttribute('aria-current', 'page'); expect(screen.getByRole('link', { name: 'Recommendation Lookup' })).not.toHaveAttribute('aria-current'); });
  it('supports keyboard navigation links', async () => { const user = userEvent.setup(); renderAt(<Agent3SectionNavigation />); await user.tab(); expect(screen.getByRole('link', { name: /New Allocation/ })).toHaveFocus(); await user.tab(); expect(screen.getByRole('link', { name: 'Recommendation Lookup' })).toHaveFocus(); });
  it('redacts a hostile render exception', () => { vi.spyOn(console, 'error').mockImplementation(() => undefined); renderAt(<Agent3ErrorBoundary><ThrowingChild /></Agent3ErrorBoundary>); expect(screen.getByRole('alert')).toHaveTextContent('temporarily unavailable'); expect(document.body).not.toHaveTextContent(/hostile-secret|postgresql|Bearer/); });
  it('offers only safe error-boundary recovery links', () => { vi.spyOn(console, 'error').mockImplementation(() => undefined); renderAt(<Agent3ErrorBoundary><ThrowingChild /></Agent3ErrorBoundary>); expect(screen.getByRole('link', { name: 'New Allocation' })).toHaveAttribute('href', '/agent3/allocations/new'); expect(screen.getByRole('link', { name: 'Recommendation Lookup' })).toHaveAttribute('href', '/agent3/recommendations/lookup'); expect(screen.queryByRole('button')).not.toBeInTheDocument(); });
  it('fails closed when the session is missing', async () => { vi.mocked(getAgent3Session).mockRejectedValue(new Error('JWT secret')); renderAt(<AllocationRequestPage />); expect(await screen.findByRole('alert')).toHaveTextContent('Authentication required'); expect(screen.queryByRole('button', { name: /Submit allocation/ })).not.toBeInTheDocument(); expect(document.body).not.toHaveTextContent('JWT secret'); });
  it('fails closed when the session is expired', async () => { vi.mocked(getAgent3Session).mockRejectedValue(new Error('expired')); renderAt(<AllocationRequestPage />); expect(await screen.findByText(/sign in through the application authentication flow/i)).toBeInTheDocument(); });
  it('does not invent a login link', async () => { vi.mocked(getAgent3Session).mockRejectedValue(new Error()); renderAt(<AllocationRequestPage />); await screen.findByRole('alert'); expect(screen.queryByRole('link', { name: /log|sign in/i })).not.toBeInTheDocument(); });
  it('uses associated form labels and a heading hierarchy', async () => { await allocation(); expect(screen.getByRole('heading', { level: 1, name: 'Create allocation request' })).toBeInTheDocument(); expect(screen.getByLabelText(/Estimated effort hours/)).toHaveAttribute('id', 'humanEstimatedEffortHours'); });
  it('contains loading and error announcements', () => { render(<><RecommendationLoadingState /><RecommendationErrorState title="Safe error" message="Try later" /></>); expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true'); expect(screen.getByRole('alert')).toHaveTextContent('Safe error'); });
  it('uses responsive form grid and bounded page classes', async () => { const { container } = await allocation(); expect(container.querySelector('.max-w-4xl')).toBeInTheDocument(); expect(container.querySelector('.sm\\:grid-cols-3')).toBeInTheDocument(); expect(container.querySelector('main')).toHaveClass('px-4'); });
  it('keeps candidate tables in keyboard-focusable overflow regions', () => { const withCandidate = structuredClone(human); withCandidate.recommendation.human_requirement_result!.eligible_candidates = [{ resource_id: '00000000-0000-0000-0000-000000000021', resource_type: 'HUMAN', name: 'Candidate', rank: 1, allocation_score: '0.90', score_breakdown: { role_match: '0.9', skill_match: '0.9', availability_score: '0.9', workload_fit: '0.9', authority_match: '0.9', total_score: '0.9' }, current_workload_percentage: '10.0', projected_workload_percentage: '20.0', available_from: '2026-01-01T00:00:00Z', available_until: null, evidence_refs: {} }]; render(<FullRecommendation response={withCandidate} />); const region = screen.getByRole('region', { name: 'Ranked human candidates table' }); expect(region).toHaveClass('overflow-x-auto'); expect(region).toHaveAttribute('tabindex', '0'); expect(screen.getByRole('table')).toHaveAccessibleName('Ranked human candidates in backend-provided order'); });
  it('wraps long UUID fields and exposes status text', () => { render(<FullRecommendation response={human} />); expect(screen.getAllByText(MOCK_RECOMMENDATION_ID)[0]).toHaveClass('break-all'); expect(screen.getByRole('status')).toHaveTextContent('Pending Human Approval'); });
  it('preserves decision ordering and offers no unsupported controls', () => { const ordered = structuredClone(human); ordered.recommendation.limitations = ['First limitation', 'Second limitation']; render(<FullRecommendation response={ordered} />); expect(document.body.textContent!.indexOf('First limitation')).toBeLessThan(document.body.textContent!.indexOf('Second limitation')); for (const name of ['Approve', 'Reject', 'Execute', 'Assign', 'Delete']) expect(screen.queryByRole('button', { name })).not.toBeInTheDocument(); });
  it('renders neither raw evidence nor unsupported AI provenance', () => { const value = structuredClone(budget); value.recommendation.budget_requirement_result!.budget_validation!.evidence_references = { secret: 'database-password' }; render(<FullRecommendation response={value} />); expect(document.body).not.toHaveTextContent('database-password'); expect(document.body).not.toHaveTextContent(/AI-generated|model-generated/i); });
  it('keeps the global network blocker effective', async () => { await expect(fetch('https://example.invalid/phase5e')).rejects.toThrow(/Network access is disabled in tests/); });
});
