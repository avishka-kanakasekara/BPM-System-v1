import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import InvoiceMatchResultView from './InvoiceMatchResultView'

describe('InvoiceMatchResultView', () => {
  it('renders MATCHED summary from backend fields', () => {
    render(
      <InvoiceMatchResultView
        result={{
          invoice_id: 'inv-1',
          purchase_order_id: 'po-1',
          process_id: 'p-1',
          tenant_id: 't-1',
          status: 'MATCHED',
          matched: true,
          invoice_amount: '110',
          po_amount: '110',
          matched_amount: '110',
          currency: 'USD',
          vendor_match: true,
          line_match: true,
        }}
      />,
    )
    expect(screen.getByText('MATCHED')).toBeInTheDocument()
    expect(screen.getByText(/Successful matching of invoice inv-1 to purchase order po-1/)).toBeInTheDocument()
    expect(screen.getByText(/Matched 110 USD/)).toBeInTheDocument()
  })

  it('renders MISMATCH discrepancy information supplied by the backend', () => {
    render(
      <InvoiceMatchResultView
        result={{
          invoice_id: 'inv-2',
          purchase_order_id: 'po-1',
          process_id: 'p-1',
          tenant_id: 't-1',
          status: 'MISMATCH',
          matched: false,
          discrepancy_codes: ['LINE_ITEM'],
          discrepancy_details: ['Affected line item qi-9: quantity 2 vs 1'],
          invoice_amount: '40',
          po_amount: '20',
          currency: 'USD',
          vendor_match: true,
          line_match: false,
        }}
      />,
    )
    expect(screen.getByText('MISMATCH')).toBeInTheDocument()
    expect(screen.getByText('Affected line item qi-9: quantity 2 vs 1')).toBeInTheDocument()
    expect(screen.getByText(/Types: LINE_ITEM/)).toBeInTheDocument()
  })
})
