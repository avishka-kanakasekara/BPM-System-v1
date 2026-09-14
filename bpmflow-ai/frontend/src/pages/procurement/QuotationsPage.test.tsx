import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import QuotationsPage from './QuotationsPage'

const PROCESS_ID = '11111111-1111-1111-1111-111111111111'

const { listProcesses, listProcessQuotations, listVendors } = vi.hoisted(() => ({
  listProcesses: vi.fn(),
  listProcessQuotations: vi.fn(),
  listVendors: vi.fn(),
}))

vi.mock('../../services/apiClient', () => ({
  listProcesses,
  listProcessQuotations,
  listVendors,
}))

describe('QuotationsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listVendors.mockResolvedValue([
      {
        vendor_id: 'vendor-1',
        tenant_id: 't1',
        vendor_code: 'V1',
        legal_name: 'Quoted Vendor',
        status: 'active',
      },
    ])
    listProcesses.mockResolvedValue([
      {
        id: PROCESS_ID,
        name: 'Laptop buy',
        process_type: 'PROCUREMENT',
        status: 'ACTIVE',
        current_stage: 'WORKFLOW_EXECUTION',
        version: 1,
        created_by: 'u1',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        tenant_id: 't1',
      },
    ])
  })

  it('renders process quotations and backend-derived count', async () => {
    listProcessQuotations.mockResolvedValue([
      {
        quotation_id: 'q1',
        tenant_id: 't1',
        quotation_number: 'QT-100',
        vendor_id: 'vendor-1',
        process_id: PROCESS_ID,
        currency: 'USD',
        subtotal: '10',
        tax: '1',
        total: '11',
        status: 'RECEIVED',
        quotation_date: '2026-03-01',
        evidence_id: 'ev-1',
        items: [
          {
            item_id: 'qi-1',
            tenant_id: 't1',
            quotation_id: 'q1',
            description: 'Laptop',
            quantity: '1',
            unit_price: '10',
            line_total: '10',
          },
        ],
      },
      {
        quotation_id: 'q2',
        tenant_id: 't1',
        quotation_number: 'QT-101',
        vendor_id: 'vendor-1',
        process_id: PROCESS_ID,
        currency: 'USD',
        subtotal: '20',
        tax: '2',
        total: '22',
        status: 'RECEIVED',
      },
    ])
    render(
      <MemoryRouter initialEntries={[`/quotations?process=${PROCESS_ID}`]}>
        <QuotationsPage />
      </MemoryRouter>,
    )
    expect(await screen.findByText('QT-100')).toBeInTheDocument()
    expect(screen.getByText('QT-101')).toBeInTheDocument()
    expect(screen.getByText(/Quotation count:/)).toHaveTextContent('2')
    expect(listProcessQuotations).toHaveBeenCalledWith(PROCESS_ID)
    expect(screen.queryByRole('button', { name: /create quotation/i })).not.toBeInTheDocument()
  })

  it('shows an empty state when the API returns no quotations', async () => {
    listProcessQuotations.mockResolvedValue([])
    render(
      <MemoryRouter initialEntries={[`/quotations?process=${PROCESS_ID}`]}>
        <QuotationsPage />
      </MemoryRouter>,
    )
    expect(await screen.findByText('No quotations')).toBeInTheDocument()
    expect(screen.getByText(/Quotation count:/)).toHaveTextContent('0')
  })
})
