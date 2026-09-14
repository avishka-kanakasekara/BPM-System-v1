import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PurchaseOrdersPage from './PurchaseOrdersPage'

const PROCESS_ID = '11111111-1111-1111-1111-111111111111'

const { listProcesses, getProcessPurchaseOrder, listVendors } = vi.hoisted(() => ({
  listProcesses: vi.fn(),
  getProcessPurchaseOrder: vi.fn(),
  listVendors: vi.fn(),
}))

vi.mock('../../services/apiClient', () => ({
  listProcesses,
  getProcessPurchaseOrder,
  listVendors,
}))

describe('PurchaseOrdersPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listVendors.mockResolvedValue([
      {
        vendor_id: 'vendor-1',
        tenant_id: 't1',
        vendor_code: 'V1',
        legal_name: 'PO Vendor',
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

  it('renders a persisted PO with process and vendor links and no create action', async () => {
    getProcessPurchaseOrder.mockResolvedValue({
      purchase_order_id: 'po-1',
      tenant_id: 't1',
      po_number: 'PO-88',
      process_id: PROCESS_ID,
      vendor_id: 'vendor-1',
      currency: 'USD',
      subtotal: '100',
      tax: '10',
      total: '110',
      status: 'ISSUED',
      selected_quotation_id: 'q-9',
      created_at: '2026-03-02T00:00:00Z',
    })
    render(
      <MemoryRouter>
        <PurchaseOrdersPage />
      </MemoryRouter>,
    )
    expect(await screen.findByText('PO-88')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Laptop buy' })).toHaveAttribute('href', `/processes/${PROCESS_ID}`)
    expect(screen.getByRole('link', { name: 'PO Vendor' })).toHaveAttribute('href', '/vendors/vendor-1')
    expect(screen.queryByRole('button', { name: /create/i })).not.toBeInTheDocument()
  })

  it('shows an empty state when no PO exists', async () => {
    getProcessPurchaseOrder.mockRejectedValue({ response: { status: 404 } })
    render(
      <MemoryRouter>
        <PurchaseOrdersPage />
      </MemoryRouter>,
    )
    expect(await screen.findByText('No purchase order yet')).toBeInTheDocument()
  })
})
