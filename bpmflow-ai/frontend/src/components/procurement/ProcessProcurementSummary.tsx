import { Link } from 'react-router-dom'
import type { InvoiceRecord, PurchaseOrderRecord, QuotationRecord, VendorRecord } from '../../types/api'
import { Panel } from '../ui/primitives'
import { invoiceMatchLabel, money } from '../../lib/procurement'

export default function ProcessProcurementSummary({
  processId,
  quotations,
  purchaseOrder,
  invoices,
  vendor,
}: {
  processId: string
  quotations: QuotationRecord[]
  purchaseOrder: PurchaseOrderRecord | null
  invoices: InvoiceRecord[]
  vendor: VendorRecord | null
}) {
  const invoice = invoices[0] ?? null
  const matching = invoice ? invoiceMatchLabel(invoice) : null
  const vendorId = purchaseOrder?.vendor_id || invoice?.vendor_id || quotations[0]?.vendor_id

  return (
    <Panel title="Procurement summary">
      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs uppercase text-slate-500">Vendor</dt>
          <dd>
            {vendorId ? (
              <Link className="link" to={`/vendors/${vendorId}`}>
                {vendor?.legal_name || vendorId}
              </Link>
            ) : (
              'Relationship information unavailable.'
            )}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-slate-500">Quotations</dt>
          <dd>
            <Link className="link" to={`/quotations?process=${processId}`}>
              {quotations.length}
            </Link>
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-slate-500">Purchase order</dt>
          <dd>
            {purchaseOrder ? (
              <Link className="link" to={`/purchase-orders/${processId}`}>
                {purchaseOrder.po_number}
              </Link>
            ) : (
              'No purchase order yet'
            )}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-slate-500">Invoice</dt>
          <dd>
            {invoice ? (
              <Link className="link" to={`/invoices/${invoice.invoice_id}`}>
                {invoice.invoice_number}
              </Link>
            ) : (
              'No invoices'
            )}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-slate-500">Matching</dt>
          <dd>{matching || 'No matching result'}</dd>
        </div>
        {invoice ? (
          <div>
            <dt className="text-xs uppercase text-slate-500">Invoice total</dt>
            <dd>{money(invoice.total, invoice.currency)}</dd>
          </div>
        ) : null}
      </dl>
      <div className="mt-4 flex flex-wrap gap-2">
        <Link className="btn btn-ghost btn-sm" to={`/quotations?process=${processId}`}>
          View quotations
        </Link>
        <Link className="btn btn-ghost btn-sm" to={`/purchase-orders/${processId}`}>
          View purchase order
        </Link>
        <Link className="btn btn-ghost btn-sm" to={`/invoices?process=${processId}`}>
          View invoices
        </Link>
      </div>
    </Panel>
  )
}
