import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import InvoicesPage from './InvoicesPage'

const PROCESS_ID = '11111111-1111-1111-1111-111111111111'

const { listProcesses, listProcessInvoices, listVendors, completeInvoiceMatching, createInvoice } = vi.hoisted(
  () => ({
    listProcesses: vi.fn(),
    listProcessInvoices: vi.fn(),
    listVendors: vi.fn(),
    completeInvoiceMatching: vi.fn(),
    createInvoice: vi.fn(),
  }),
)

const authState = vi.hoisted(() => ({
  user: {
    id: 'user-1',
    email: 'a@example.com',
    role: 'approver' as string,
    tenant_id: '00000000-0000-0000-0000-000000000001',
  },
}))

vi.mock('../../auth/AuthContext', () => ({
  useAuth: () => ({
    user: authState.user,
    session: { access_token: 'test' },
    loading: false,
    error: null,
    signIn: vi.fn(),
    signUp: vi.fn(),
    signOut: vi.fn(),
    refreshProfile: vi.fn(),
  }),
}))

vi.mock('../../services/apiClient', () => ({
  listProcesses,
  listProcessInvoices,
  listVendors,
  completeInvoiceMatching,
  createInvoice,
}))

describe('InvoicesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState.user.role = 'approver'
    listVendors.mockResolvedValue([])
    listProcesses.mockResolvedValue([
      {
        id: PROCESS_ID,
        name: 'Laptop buy',
        process_type: 'PROCUREMENT',
        status: 'ACTIVE',
        current_stage: 'INVOICE_MATCHING',
        version: 1,
        created_by: 'u1',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        tenant_id: authState.user.tenant_id,
      },
    ])
    completeInvoiceMatching.mockResolvedValue({ success: true, message: 'ok', current_stage: 'COMPLETED' })
  })

  it('renders persisted invoice data and matching status', async () => {
    listProcessInvoices.mockResolvedValue([
      {
        invoice_id: 'inv-1',
        tenant_id: authState.user.tenant_id,
        invoice_number: 'INV-55',
        vendor_id: 'vendor-1',
        purchase_order_id: 'po-1',
        process_id: PROCESS_ID,
        currency: 'USD',
        subtotal: '80',
        tax: '8',
        total: '88',
        status: 'MATCHED',
        invoice_date: '2026-04-01',
        received_at: '2026-04-02T00:00:00Z',
        match_result: {
          matched: true,
          status: 'MATCHED',
          invoice_amount: '88',
          po_amount: '88',
          currency: 'USD',
          vendor_match: true,
          line_match: true,
        },
      },
    ])
    render(
      <MemoryRouter>
        <InvoicesPage />
      </MemoryRouter>,
    )
    expect(await screen.findByText('INV-55')).toBeInTheDocument()
    expect(screen.getAllByText('MATCHED').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/88 USD/).length).toBeGreaterThan(0)
    expect(screen.queryByText('Persist invoice (admin)')).not.toBeInTheDocument()
  })

  it('matches using the persisted invoice flow without expected_* values', async () => {
    listProcessInvoices.mockResolvedValue([
      {
        invoice_id: 'inv-1',
        tenant_id: authState.user.tenant_id,
        invoice_number: 'INV-55',
        vendor_id: 'vendor-1',
        purchase_order_id: 'po-1',
        process_id: PROCESS_ID,
        currency: 'USD',
        subtotal: '80',
        tax: '8',
        total: '88',
        status: 'RECEIVED',
      },
    ])
    render(
      <MemoryRouter>
        <InvoicesPage />
      </MemoryRouter>,
    )
    await screen.findByText('INV-55')
    await userEvent.click(screen.getByRole('button', { name: 'Match persisted invoice' }))
    await waitFor(() => expect(completeInvoiceMatching).toHaveBeenCalledWith(PROCESS_ID, {}))
    const payload = completeInvoiceMatching.mock.calls[0][1]
    expect(payload).toEqual({})
    expect(JSON.stringify(payload)).not.toMatch(/expected_/)
  })

  it('renders a MISMATCH result with discrepancy details from the backend', async () => {
    listProcessInvoices.mockResolvedValue([
      {
        invoice_id: 'inv-2',
        tenant_id: authState.user.tenant_id,
        invoice_number: 'INV-56',
        vendor_id: 'vendor-1',
        purchase_order_id: 'po-1',
        process_id: PROCESS_ID,
        currency: 'USD',
        subtotal: '90',
        tax: '9',
        total: '99',
        status: 'MISMATCH',
        match_result: {
          matched: false,
          status: 'MISMATCH',
          discrepancy_codes: ['AMOUNT'],
          discrepancy_details: ['Invoice total 99 does not equal PO total 88'],
          invoice_amount: '99',
          po_amount: '88',
          currency: 'USD',
          vendor_match: true,
          line_match: false,
        },
      },
    ])
    render(
      <MemoryRouter>
        <InvoicesPage />
      </MemoryRouter>,
    )
    expect(await screen.findByText('INV-56')).toBeInTheDocument()
    expect(screen.getAllByText('MISMATCH').length).toBeGreaterThan(0)
    expect(screen.getByText('Invoice total 99 does not equal PO total 88')).toBeInTheDocument()
    expect(screen.getByText(/Types: AMOUNT/)).toBeInTheDocument()
  })

  it('shows empty state when no invoices exist', async () => {
    listProcessInvoices.mockResolvedValue([])
    render(
      <MemoryRouter>
        <InvoicesPage />
      </MemoryRouter>,
    )
    expect(await screen.findByText('No invoices')).toBeInTheDocument()
  })
})
