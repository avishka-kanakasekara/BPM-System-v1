import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TobeRecommendationsPage from './TobeRecommendationsPage'
import TobeRecommendationDetailPage from './TobeRecommendationDetailPage'

const {
  listProcesses,
  listTobeRecommendations,
  generateTobeRecommendations,
  getTobeRecommendation,
  reviewTobeRecommendation,
} = vi.hoisted(() => ({
  listProcesses: vi.fn(),
  listTobeRecommendations: vi.fn(),
  generateTobeRecommendations: vi.fn(),
  getTobeRecommendation: vi.fn(),
  reviewTobeRecommendation: vi.fn(),
}))

const authState = vi.hoisted(() => ({
  user: { id: 'u1', email: 'a@example.com', role: 'approver' as string, tenant_id: 't1' },
}))

vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({
    user: authState.user,
    session: { access_token: 't' },
    loading: false,
    error: null,
    signIn: vi.fn(),
    signUp: vi.fn(),
    signOut: vi.fn(),
    refreshProfile: vi.fn(),
  }),
}))

vi.mock('../services/apiClient', () => ({
  listProcesses,
  listTobeRecommendations,
  generateTobeRecommendations,
  getTobeRecommendation,
  reviewTobeRecommendation,
}))

const PROCESS_ID = '11111111-1111-1111-1111-111111111111'

const rec = {
  id: 'rec-1',
  tenant_id: 't1',
  process_id: PROCESS_ID,
  recommendation_type: 'BOTTLENECK',
  title: 'Shorten finance wait',
  description: 'Parallelize review',
  reason: 'Approver wait is long',
  evidence: [{ field: 'average_wait_seconds', value: '90', source: 'monitoring' }],
  expected_benefit: 'Lower wait',
  confidence: '0.8',
  status: 'PROPOSED',
  fingerprint: 'fp',
  created_at: '2026-01-05T00:00:00Z',
  activates_workflow: false,
}

describe('TO-BE recommendations', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState.user.role = 'approver'
    listProcesses.mockResolvedValue([
      {
        id: PROCESS_ID,
        name: 'Laptop buy',
        process_type: 'PROCUREMENT',
        status: 'COMPLETED',
        current_stage: 'COMPLETED',
        version: 1,
        created_by: 'u1',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        tenant_id: 't1',
      },
    ])
    listTobeRecommendations.mockResolvedValue([rec])
  })

  it('renders recommendations and evidence and does not generate on open', async () => {
    render(
      <MemoryRouter initialEntries={[`/recommendations?process=${PROCESS_ID}`]}>
        <TobeRecommendationsPage />
      </MemoryRouter>,
    )
    expect(await screen.findByText('Shorten finance wait')).toBeInTheDocument()
    expect(screen.getByText(/average_wait_seconds: 90/)).toBeInTheDocument()
    expect(generateTobeRecommendations).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Generate recommendations' })).toBeInTheDocument()
  })

  it('generate is an explicit action', async () => {
    generateTobeRecommendations.mockResolvedValue([rec])
    render(
      <MemoryRouter initialEntries={[`/recommendations?process=${PROCESS_ID}`]}>
        <TobeRecommendationsPage />
      </MemoryRouter>,
    )
    await screen.findByText('Shorten finance wait')
    await userEvent.click(screen.getByRole('button', { name: 'Generate recommendations' }))
    await waitFor(() => expect(generateTobeRecommendations).toHaveBeenCalledWith(PROCESS_ID))
  })

  it('accept review uses the backend API and does not activate a workflow', async () => {
    getTobeRecommendation.mockResolvedValue(rec)
    reviewTobeRecommendation.mockResolvedValue({ ...rec, status: 'ACCEPTED' })
    render(
      <MemoryRouter initialEntries={['/recommendations/rec-1']}>
        <Routes>
          <Route path="/recommendations/:recommendationId" element={<TobeRecommendationDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )
    await screen.findByText('Shorten finance wait')
    await userEvent.click(screen.getByRole('button', { name: 'Accept' }))
    await waitFor(() =>
      expect(reviewTobeRecommendation).toHaveBeenCalledWith('rec-1', { decision: 'ACCEPTED', comment: undefined }),
    )
    expect(screen.queryByRole('button', { name: /implement/i })).not.toBeInTheDocument()
    expect(await screen.findByText(/no workflow was activated/i)).toBeInTheDocument()
  })
})
