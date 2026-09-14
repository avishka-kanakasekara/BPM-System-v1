import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ExceptionsPage from './ExceptionsPage'

const { listExceptions, listProcesses } = vi.hoisted(() => ({
  listExceptions: vi.fn(),
  listProcesses: vi.fn(),
}))

vi.mock('../services/apiClient', () => ({
  listExceptions,
  listProcesses,
}))

describe('ExceptionsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listProcesses.mockResolvedValue([
      {
        id: 'p1',
        name: 'Laptop buy',
        process_type: 'PROCUREMENT',
        status: 'EXCEPTION',
        current_stage: 'EXCEPTION',
        version: 1,
        created_by: 'u1',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        tenant_id: 't1',
      },
    ])
  })

  it('renders exceptions from the API', async () => {
    listExceptions.mockResolvedValue([
      {
        id: 'ex-1',
        process_id: 'p1',
        exception_code: 'INVOICE_MISMATCH',
        title: 'Totals differ',
        severity: 'high',
        type: 'INVOICE_MISMATCH',
        description: 'Invoice total mismatch',
        status: 'open',
        created_at: '2026-01-04T00:00:00Z',
      },
    ])
    render(
      <MemoryRouter>
        <ExceptionsPage />
      </MemoryRouter>,
    )
    expect(await screen.findByText('INVOICE_MISMATCH')).toBeInTheDocument()
    expect(screen.getByText('Totals differ')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'INVOICE_MISMATCH' })).toHaveAttribute('href', '/exceptions/ex-1')
  })

  it('shows an empty state', async () => {
    listExceptions.mockResolvedValue([])
    render(
      <MemoryRouter>
        <ExceptionsPage />
      </MemoryRouter>,
    )
    expect(await screen.findByText('No exceptions')).toBeInTheDocument()
  })
})
