import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import Agent2RecommendationsPage from './RecommendationsPage'

vi.mock('../../auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', role: 'admin' },
    session: { access_token: 't' },
    loading: false,
    error: null,
    signIn: vi.fn(),
    signUp: vi.fn(),
    signOut: vi.fn(),
    refreshProfile: vi.fn(),
  }),
}))

vi.mock('../../services/apiClient', () => ({
  apiErrorMessage: () => 'failed',
  listOptimizationRecommendations: vi.fn().mockResolvedValue([]),
  decideOptimization: vi.fn(),
}))

describe('Agent2RecommendationsPage', () => {
  it('is labeled as Agent 2 optimization recommendations, not TO-BE', async () => {
    render(
      <MemoryRouter>
        <Agent2RecommendationsPage />
      </MemoryRouter>,
    )
    expect(await screen.findByText('Agent 2 Optimization Recommendations')).toBeInTheDocument()
    expect(
      screen.getByText(/These are Agent 2 execution\/optimization recommendations and are separate from BPMFlow AI TO-BE process recommendations/),
    ).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'TO-BE Process Recommendations' })).not.toBeInTheDocument()
  })
})
