import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ExceptionDetailPage from './ExceptionDetailPage'

const { getException, getProcess, resolveException, retryException, failException } = vi.hoisted(() => ({
  getException: vi.fn(),
  getProcess: vi.fn(),
  resolveException: vi.fn(),
  retryException: vi.fn(),
  failException: vi.fn(),
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
  getException,
  getProcess,
  resolveException,
  retryException,
  failException,
}))

const exception = {
  id: 'ex-1',
  process_id: 'p1',
  exception_code: 'INVOICE_MISMATCH',
  title: 'Totals differ',
  severity: 'high',
  type: 'INVOICE_MISMATCH',
  description: 'Invoice total mismatch',
  status: 'open',
  created_at: '2026-01-04T00:00:00Z',
  details: { discrepancy: 'AMOUNT' },
  evidence_refs: ['ev-1'],
  workflow_step_id: 'step-9',
}

async function renderDetail() {
  getException.mockResolvedValue(exception)
  getProcess.mockResolvedValue({
    id: 'p1',
    name: 'Laptop buy',
    current_stage: 'EXCEPTION',
    status: 'EXCEPTION',
  })
  render(
    <MemoryRouter initialEntries={['/exceptions/ex-1']}>
      <Routes>
        <Route path="/exceptions/:exceptionId" element={<ExceptionDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
  await screen.findByText('Totals differ')
}

describe('ExceptionDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState.user.role = 'approver'
  })

  it('renders exception detail', async () => {
    await renderDetail()
    expect(screen.getByText('Invoice total mismatch')).toBeInTheDocument()
    expect(screen.getByText(/discrepancy: AMOUNT/)).toBeInTheDocument()
    expect(screen.getByText('ev-1')).toBeInTheDocument()
    expect(screen.getByText(/step-9/)).toBeInTheDocument()
  })

  it('resolve uses the backend API', async () => {
    resolveException.mockResolvedValue({ exception: { ...exception, status: 'resolved', resolution_notes: 'ok' } })
    await renderDetail()
    await userEvent.type(screen.getByPlaceholderText(/Required for resolve/), 'Fixed')
    await userEvent.click(screen.getByRole('button', { name: 'Resolve' }))
    await waitFor(() => expect(resolveException).toHaveBeenCalledWith('ex-1', 'Fixed'))
  })

  it('retry uses the backend API', async () => {
    retryException.mockResolvedValue({ exception: { ...exception, status: 'in_progress' } })
    await renderDetail()
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(retryException).toHaveBeenCalledWith('ex-1', undefined))
  })

  it('fail uses the backend API', async () => {
    failException.mockResolvedValue({ exception: { ...exception, status: 'ignored' } })
    await renderDetail()
    await userEvent.type(screen.getByPlaceholderText(/Required for resolve/), 'Cannot recover')
    await userEvent.click(screen.getByRole('button', { name: 'Fail' }))
    await waitFor(() => expect(failException).toHaveBeenCalledWith('ex-1', 'Cannot recover'))
  })

  it('hides restricted actions from a requester', async () => {
    authState.user.role = 'requester'
    await renderDetail()
    expect(screen.queryByRole('button', { name: 'Resolve' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Fail' })).not.toBeInTheDocument()
  })
})
